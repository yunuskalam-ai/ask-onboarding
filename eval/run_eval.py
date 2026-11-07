"""Evaluate retrieval and answers on the held-out question set.

For each chunk size, the sample docs are indexed into a separate
<db>_eval database (dev data is never touched). Then:

  Retrieval (fast, no LLM), for every chunk size and top_k:
    hit@k            the expected document is among the top k chunks
  Answers (slow: one LLM call per question), for each --answer-config:
    accuracy         answerable question, not refused, contains every key fact
    cites source     the answer cites the expected document
    false refusals   answerable question answered "not in the documents"
    refusal accuracy unanswerable question correctly refused
    first token      seconds until the first word (median)

Answers are scored by key facts, not by an LLM judge: a 3B model is not a
reliable grader, and fact matching gives the same score on every run.
Every answer is printed so the scoring can be spot-checked.

Run inside the api container (it has the models and the database):
    docker compose exec api python /app/eval/run_eval.py
    docker compose exec api python /app/eval/run_eval.py --answer-configs 800:5,800:3
    docker compose exec api python /app/eval/run_eval.py --retrieval-only
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.chat.service import answer_events  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import connect, ensure_database, sibling_database_url  # noqa: E402
from app.ingest.service import ingest_file  # noqa: E402
from app.retrieval.search import retrieve, search  # noqa: E402

SAMPLE_DOCS = ROOT / "sample_docs"
RESULTS = ROOT / "eval" / "results"
OVERLAP = {400: 50, 800: 100}  # overlap must stay under half the chunk size


def load_questions() -> list[dict]:
    return json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]


def index(conn, chunk_size: int) -> int:
    conn.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
    for path in sorted(SAMPLE_DOCS.iterdir()):
        ingest_file(conn, path.name, path.read_bytes(), chunk_size=chunk_size, chunk_overlap=OVERLAP[chunk_size])
    return conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]


def retrieval_scores(conn, questions: list[dict], ks: list[int]) -> dict[int, float]:
    answerable = [q for q in questions if q["source"]]
    hits = {k: 0 for k in ks}
    for q in answerable:
        files = [h.filename for h in search(conn, q["question"], top_k=max(ks))]
        for k in ks:
            hits[k] += q["source"] in files[:k]
    return {k: hits[k] / len(answerable) for k in ks}


def contains_facts(answer: str, groups: list[list[str]]) -> bool:
    text = answer.lower()
    return all(any(alt.lower() in text for alt in group) for group in groups)


def ask(conn, q: dict, top_k: int) -> dict:
    start = time.perf_counter()
    retrieval = retrieve(conn, q["question"], top_k=top_k)
    first = None
    text, done, error = "", None, None
    for name, data in answer_events(q["question"], retrieval):
        if name == "token":
            first = first or time.perf_counter() - start
            text += data["text"]
        elif name == "done":
            done = data
        elif name == "error":
            error = data["message"]
    answered = bool(done and done["answered"])
    cited = {c["filename"] for c in done["citations"]} if done else set()
    return {
        "id": q["id"],
        "answer": text.strip(),
        "reason": done["reason"] if done else "error",
        "error": error,
        "answered": answered,
        "correct": bool(q["source"]) and answered and contains_facts(text, q["must_include"]),
        "cites_source": bool(q["source"]) and q["source"] in cited,
        "refused_correctly": not q["source"] and not answered and error is None,
        "first_token_s": round(first, 1) if first is not None else None,
        "total_s": round(time.perf_counter() - start, 1),
    }


def answer_scores(results: list[dict], questions: list[dict]) -> dict:
    answerable = [r for r, q in zip(results, questions) if q["source"]]
    unanswerable = [r for r, q in zip(results, questions) if not q["source"]]
    llm_times = [r["first_token_s"] for r in results if r["first_token_s"] and r["reason"] != "low_score"]
    return {
        "accuracy": sum(r["correct"] for r in answerable) / len(answerable),
        "cites_source": sum(r["cites_source"] for r in answerable) / len(answerable),
        "false_refusals": sum(not r["answered"] for r in answerable),
        "refusal_accuracy": sum(r["refused_correctly"] for r in unanswerable) / len(unanswerable),
        "errors": sum(r["error"] is not None for r in results),
        "median_first_token_s": statistics.median(llm_times) if llm_times else None,
    }


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chunk-sizes", default="400,800", help="characters, comma-separated (400 and/or 800)")
    parser.add_argument("--answer-configs", default="800:5,800:3", help="chunk_size:top_k pairs to run answers for")
    parser.add_argument("--retrieval-only", action="store_true", help="skip the slow LLM part")
    args = parser.parse_args()

    questions = load_questions()
    chunk_sizes = [int(s) for s in args.chunk_sizes.split(",")]
    answer_configs = [] if args.retrieval_only else [tuple(map(int, c.split(":"))) for c in args.answer_configs.split(",")]
    for size, _ in answer_configs:
        if size not in chunk_sizes:
            chunk_sizes.append(size)

    url = sibling_database_url("eval")
    ensure_database(url)
    provider = settings.ollama_model if settings.llm_provider == "ollama" else settings.answer_model
    report = {"when": datetime.now().isoformat(timespec="seconds"), "llm": provider, "min_score": settings.min_score,
              "retrieval": {}, "answers": {}}

    print(f"# Eval: {len(questions)} questions, LLM {provider}, MIN_SCORE {settings.min_score}\n")
    print("## Retrieval (16 answerable questions)\n")
    print("| Chunk size | Chunks | hit@1 | hit@3 | hit@5 |")
    print("| --- | --- | --- | --- | --- |")
    with connect(url) as conn:
        for size in chunk_sizes:
            n_chunks = index(conn, size)
            scores = retrieval_scores(conn, questions, [1, 3, 5])
            report["retrieval"][size] = {"chunks": n_chunks, **{f"hit@{k}": v for k, v in scores.items()}}
            print(f"| {size} chars | {n_chunks} | {pct(scores[1])} | {pct(scores[3])} | {pct(scores[5])} |", flush=True)

            for c_size, top_k in answer_configs:
                if c_size != size:
                    continue
                label = f"{size}:{top_k}"
                print(f"\n### Answers with {size}-char chunks, top {top_k} sources\n", flush=True)
                results = []
                for q in questions:
                    r = ask(conn, q, top_k)
                    results.append(r)
                    mark = "ok " if (r["correct"] or r["refused_correctly"]) else "BAD"
                    cite = "cite" if r["cites_source"] else "    "
                    shown = r["error"] or r["answer"].replace("\n", " ")[:110]
                    print(f"- {mark} {cite} {r['total_s']:5.1f}s `{q['id']}` {shown}", flush=True)
                report["answers"][label] = {"scores": answer_scores(results, questions), "results": results}
                print()

    if report["answers"]:
        print("## Answers\n")
        print("| Chunks : sources | Accuracy (16) | Cites right doc | False refusals | Refusal accuracy (4) | Median first token |")
        print("| --- | --- | --- | --- | --- | --- |")
        for label, data in report["answers"].items():
            s = data["scores"]
            ft = f"{s['median_first_token_s']:.1f} s" if s["median_first_token_s"] else "-"
            print(f"| {label} | {pct(s['accuracy'])} | {pct(s['cites_source'])} | {s['false_refusals']} | "
                  f"{pct(s['refusal_accuracy'])} | {ft} |")

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull results: eval/results/{out.name}")


if __name__ == "__main__":
    main()

# Ask Onboarding

Ask Onboarding is a RAG assistant that answers new employees' questions from company documents. Every answer cites the exact passage it came from. When the documents don't cover a question, the app says "I don't know" and offers to open a help-desk ticket instead.

**Stack:** FastAPI · Postgres 16 + pgvector · fastembed (local embeddings) · Ollama with qwen2.5:3b (local LLM; Claude optional) · React + Vite + TypeScript · Docker Compose

Everything runs locally. No API key is needed.

> Status: work in progress. All core features and the evaluation are done; hybrid search and the architecture write-up come next.

## Quick start

```bash
git clone https://github.com/yunuskalam-ai/ask-onboarding.git
cd ask-onboarding
docker compose up
```

This starts Postgres (with pgvector), Ollama, the API and the web app.

**Open http://localhost:8080.** The 18 sample documents load automatically on the first start (watch them turn *ready* on the Documents page, about a minute). Then ask questions on the Chat page, upload your own files on the Documents page, and see help-desk tickets for unanswered questions on the Tickets page.

**The first start takes a few minutes:** it downloads the Ollama image and the `qwen2.5:3b` model (about 1.9 GB). The API waits until the model is ready. Later starts take seconds.

The model runs on the CPU, so the first words of an answer take a few seconds. To use Claude instead, copy `.env.example` to `.env`, then set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

- API docs (try the endpoints): http://localhost:8000/docs
- Upload a file: `curl -F "file=@sample_docs/faq-payroll.txt" localhost:8000/api/documents`
- See document status: `curl localhost:8000/api/documents`
- Ask a question (streams Server-Sent Events): `curl -N -H "Content-Type: application/json" -d '{"question": "Can I deploy on a Friday?"}' localhost:8000/api/chat`

## Running the tests

Tests need the database running (`docker compose up -d db`). They use a separate `ask_onboarding_test` database, so your data is not touched.

```bash
# inside Docker
docker compose exec api python -m pytest

# or locally
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m pytest
```

Frontend tests (stream parser and answer rendering):

```bash
cd frontend
npm ci
npm test
```

## Project layout

| Path | Contents |
| --- | --- |
| `backend/app/` | FastAPI app: ingestion, retrieval, chat, tickets |
| `backend/tests/` | pytest tests |
| `frontend/` | React app: Upload, Chat and Tickets pages |
| `eval/` | 20-question evaluation set and scoring script |
| `sample_docs/` | Sample company documents, loaded on first start |
| `scripts/` | Helper scripts, such as the generator for the sample PDFs |
| `db/init.sql` | Enables the pgvector extension |

## Sample data

`sample_docs/` holds 18 documents for **Larkspur Labs**, a made-up 300-person software company. There are 12 Markdown files, 4 text files and 2 multi-page PDFs, covering the employee handbook, the engineering wiki, IT guides and office information. Every name, address and email in them is fictional (`*.example` domains).

Regenerate the PDFs with `pip install fpdf2==2.8.3 && python scripts/make_sample_pdfs.py`.

## Evaluation

**Result with the defaults (400-character chunks, top 5 sources, qwen2.5:3b on CPU):** 15 of 16 answerable questions answered correctly, all 4 unanswerable questions refused, and no false "I don't know" answers.

[eval/questions.json](eval/questions.json) has 20 held-out questions. None of them were used to tune anything. 16 are answerable: they cover every document type, both PDFs, and some paraphrased questions ("holiday" for "annual leave"). 4 are not in the documents (stock options, company car, dogs, sabbaticals). An answer counts as correct when it is not a refusal and contains every key fact, like "25" or "Tuesday" and "Thursday". This check is strict and gives the same score on every run. A 3B model would be an unreliable LLM judge, and the script prints every answer so the scoring can be checked by hand.

| Chunks : sources | Accuracy (16) | Cites the right doc | False refusals | Refusal accuracy (4) | Prompt size | Median first token |
| --- | --- | --- | --- | --- | --- | --- |
| **400 : 5** (default) | **94%** | **94%** | 0 | **100%** | **1,966 chars** | **7.7 s** |
| 800 : 5 | 88% | 81% | 0 | 100% | 3,598 chars | 10.9 s |

Retrieval found the expected document in the top 3 for all 16 answerable questions, at both chunk sizes (hit@1 94%).

What the eval changed:

- **The chunk size went from 800 to 400.** It was better on every answer metric in two separate runs, and the prompt is 45% smaller, so answers start about 3 s sooner on a CPU. The cost: smaller chunks lose some context. On the calibration set, "Is there car parking at the London office?" now ranks its document 3rd instead of 1st, because the parking chunk no longer includes the LONDON heading. The model reads the top 5, so the answer is unaffected.
- **Paraphrased refusals are now detected.** The first run showed the model sometimes refuses in its own words ("The provided sources do not mention stock options"). Those counted as answers, so the UI offered no ticket. They are now caught, but only when the answer cites nothing.
- **Timing is measured fairly.** One run showed a 1.5 s first token that came from Ollama reusing a cached prompt start from the previous config. Prompt size is now reported too, as a repeatable speed measure.

The remaining miss: "Which days should I be in the office?" is answered with core hours instead of the Tuesday/Thursday anchor days. The right document is retrieved, so this is the 3B model's limit.

The "no answer" threshold (`MIN_SCORE=0.55`) was set separately with [eval/calibrate_threshold.py](eval/calibrate_threshold.py). Answerable questions score 0.61–0.82 and off-topic ones 0.44–0.53. Near-topic questions the documents don't answer score like answerable ones (0.61–0.66), so the prompt's refusal rule has to catch them.

Run it yourself (about 10 minutes on a laptop CPU; Git Bash on Windows needs `MSYS_NO_PATHCONV=1` in front):

```bash
docker compose exec api python /app/eval/run_eval.py                   # retrieval + answers for 400:5 and 800:5
docker compose exec api python /app/eval/run_eval.py --retrieval-only  # seconds, no LLM
```

It uses a separate `ask_onboarding_eval` database and writes full results to `eval/results/`. After changing `CHUNK_SIZE` for the app itself, run `docker compose exec api python -m app.reindex`.

## Docs

These sections are written as the project progresses:

- Known limitations
- `ARCHITECTURE.md`: design, tradeoffs and scaling plan
- `AI_LOG.md`: how AI tools were used

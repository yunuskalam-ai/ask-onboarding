"""Measure retrieval scores to choose MIN_SCORE, the "no answer" threshold.

Runs three groups of questions against the running API:
  answerable  - the sample docs answer them (expected file given)
  near-topic  - sound like company questions, but no doc answers them
  off-topic   - nothing to do with the company

and prints the best score for each, plus whether the expected document
was retrieved. A good threshold sits below every answerable score and
above the off-topic scores. Near-topic questions usually score like
answerable ones, so the LLM prompt's refusal rule must catch those.

Usage (with `docker compose up` running and the sample docs uploaded):
    python eval/calibrate_threshold.py [--api http://localhost:8000]

Standard library only, so it runs without installing anything.
"""

import argparse
import http.cookiejar
import json
import urllib.request

# Keeps the session cookie between requests, like a browser.
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

ANSWERABLE = [
    ("How many days of annual leave do I get?", "handbook-pto-and-leave-policy.md"),
    ("What time should I arrive on my first day?", "handbook-welcome-and-first-week.md"),
    ("How much is the home office allowance?", "handbook-remote-and-hybrid-work.md"),
    ("What is the hotel limit in London?", "handbook-expenses-and-travel.md"),
    ("How much does the company contribute to my pension?", "handbook-benefits-overview.md"),
    ("How long must my password be?", "it-password-reset-steps.txt"),
    ("Do I need the VPN for Slack?", "it-vpn-and-wifi.md"),
    ("How many approvals does a PR touching payments need?", "eng-code-review-guidelines.md"),
    ("Can I deploy to production on a Friday?", "eng-deployment-and-releases.md"),
    ("How much is the on-call allowance?", "eng-on-call-and-incidents.md"),
    ("Do I have to declare a gift from a supplier?", "handbook-code-of-conduct.pdf"),
    ("When are promotions decided?", "handbook-performance-reviews.pdf"),
    ("When is payday?", "faq-payroll.txt"),
    ("How many people fit in the Kestrel room?", "office-meeting-room-booking.txt"),
    ("Is there car parking at the London office?", "office-guide-london-and-manchester.txt"),
    ("What laptop do engineers get?", "it-laptop-and-accounts.md"),
]
NEAR_TOPIC = [
    "Do employees get stock options?",
    "Can I get a company car?",
    "Can I bring my dog to the office?",
    "How do I apply for a sabbatical?",
]
OFF_TOPIC = [
    "What is the capital of France?",
    "Write me a poem about the sea",
    "Who won the football world cup in 2022?",
    "How do I bake sourdough bread?",
]


def _post(url: str, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with OPENER.open(request) as response:
        return json.load(response)


def sign_in(api: str) -> None:
    """The API needs a session. Any account can search; use the first one listed."""
    with OPENER.open(f"{api}/api/auth/accounts") as response:
        email = json.load(response)[0]["email"]
    _post(f"{api}/api/auth/sign-in", {"email": email})


def retrieve(api: str, question: str) -> dict:
    return _post(f"{api}/api/retrieve", {"question": question, "top_k": 5})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    api = parser.parse_args().api
    sign_in(api)

    groups = {"answerable": [], "near-topic": [], "off-topic": []}
    hit_at_1 = hit_at_5 = 0

    print(f"{'group':11} {'best':>5}  rank  question")
    for question, expected in ANSWERABLE:
        hits = retrieve(api, question)["hits"]
        files = [h["filename"] for h in hits]
        rank = files.index(expected) + 1 if expected in files else None
        hit_at_1 += rank == 1
        hit_at_5 += rank is not None
        groups["answerable"].append(hits[0]["score"])
        print(f"{'answerable':11} {hits[0]['score']:.3f}  {rank or '-':>4}  {question}")
    for name, questions in (("near-topic", NEAR_TOPIC), ("off-topic", OFF_TOPIC)):
        for question in questions:
            score = retrieve(api, question)["hits"][0]["score"]
            groups[name].append(score)
            print(f"{name:11} {score:.3f}     -  {question}")

    print()
    for name, scores in groups.items():
        print(f"{name:11} best score range {min(scores):.3f} - {max(scores):.3f}")
    n = len(ANSWERABLE)
    print(f"hit@1 {hit_at_1}/{n}, hit@5 {hit_at_5}/{n}")
    print(
        f"A threshold between {max(groups['off-topic']):.3f} and {min(groups['answerable']):.3f} "
        "blocks all off-topic questions without blocking any answerable one."
    )


if __name__ == "__main__":
    main()

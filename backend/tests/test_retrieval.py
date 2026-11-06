"""Retrieval with the real embedding model over all 18 sample docs.

Uses the `indexed` fixture from conftest. Tests here must leave the data
as they found it.
"""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_database_url
from app.main import app
from app.retrieval.search import retrieve, search


@pytest.mark.parametrize(
    "question, expected_file",
    [
        ("How many days of annual leave do I get?", "handbook-pto-and-leave-policy.md"),
        ("Can I deploy to production on a Friday?", "eng-deployment-and-releases.md"),
        ("How long must my password be?", "it-password-reset-steps.txt"),
        ("Is there car parking at the London office?", "office-guide-london-and-manchester.txt"),
        ("When are promotions decided?", "handbook-performance-reviews.pdf"),
    ],
)
def test_known_question_finds_its_document_first(indexed, question, expected_file):
    hits = search(indexed, question)
    assert hits[0].filename == expected_file


def test_hits_are_sorted_and_limited_to_top_k(indexed):
    hits = search(indexed, "What does the security policy say about USB sticks?", top_k=3)

    assert len(hits) == 3
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)


def test_pdf_hit_carries_its_page_number(indexed):
    [hit] = search(indexed, "Do I have to declare a gift from a supplier?", top_k=1)

    assert hit.filename == "handbook-code-of-conduct.pdf"
    assert hit.page == 3
    assert "£50" in hit.text


def test_on_topic_question_is_answerable(indexed):
    assert retrieve(indexed, "How much is the home office allowance?").answerable


def test_off_topic_question_is_not_answerable(indexed):
    result = retrieve(indexed, "Who won the football world cup in 2022?")

    assert not result.answerable
    assert result.hits  # the hits are still returned, for debugging
    assert result.hits[0].score < result.min_score


def test_documents_that_are_not_ready_are_never_returned(indexed):
    question = "How many days of annual leave do I get?"
    target = "handbook-pto-and-leave-policy.md"
    indexed.execute("UPDATE documents SET status = 'failed' WHERE filename = %s", (target,))
    try:
        filenames = {hit.filename for hit in search(indexed, question, top_k=20)}
        assert target not in filenames
    finally:
        indexed.execute("UPDATE documents SET status = 'ready' WHERE filename = %s", (target,))


# --- API ------------------------------------------------------------------

@pytest.fixture
def client(indexed, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_retrieve_endpoint_returns_scored_sources(client):
    response = client.post("/api/retrieve", json={"question": "When is payday?", "top_k": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["answerable"] is True
    assert len(body["hits"]) == 2
    first = body["hits"][0]
    assert first["filename"] == "faq-payroll.txt"
    assert {"page", "start_char", "end_char", "text", "score"} <= first.keys()


@pytest.mark.parametrize(
    "payload",
    [{"question": ""}, {"question": "   "}, {"question": "x" * 1001}, {"question": "hi", "top_k": 0}, {"question": "hi", "top_k": 21}],
)
def test_retrieve_endpoint_validates_input(client, payload):
    assert client.post("/api/retrieve", json=payload).status_code == 422

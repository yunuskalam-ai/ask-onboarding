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
def test_known_question_finds_its_document_in_the_top_3(indexed, question, expected_file):
    # The LLM reads the top 5 sources, so rank 1 is not required. With
    # 400-char chunks "car parking" ranks 3rd: the parking text sits in a
    # chunk that no longer includes the LONDON heading. eval/run_eval.py
    # tracks hit@1 separately.
    files = [hit.filename for hit in search(indexed, question, top_k=3)]
    assert expected_file in files


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


# --- Hybrid search (vector + keyword, Reciprocal Rank Fusion) -----------------

def test_hybrid_restores_the_keyword_match_that_vector_search_ranks_third(indexed):
    question = "Is there car parking at the London office?"
    vector = [h.filename for h in search(indexed, question, top_k=3, mode="vector")]
    hybrid = [h.filename for h in search(indexed, question, top_k=3, mode="hybrid")]

    assert vector[0] != "office-guide-london-and-manchester.txt"
    assert hybrid[0] == "office-guide-london-and-manchester.txt"


def test_hybrid_returns_each_chunk_once_and_at_most_top_k(indexed):
    hits = search(indexed, "How many approvals does a pull request need?", top_k=5, mode="hybrid")

    assert len(hits) == 5
    assert len({h.chunk_id for h in hits}) == 5


def test_hybrid_scores_are_still_cosine_similarity(indexed):
    question = "How much is the home office allowance?"
    vector = {h.chunk_id: h.score for h in search(indexed, question, top_k=20, mode="vector")}
    for hit in search(indexed, question, top_k=5, mode="hybrid"):
        if hit.chunk_id in vector:
            assert hit.score == pytest.approx(vector[hit.chunk_id])


def test_keyword_matches_cannot_lift_a_question_over_the_threshold(indexed):
    # "Kestrel" matches the meeting room by keyword, but the guard only trusts similarity.
    result = retrieve(indexed, "How many people fit in the Kestrel room?", min_score=0.99, mode="hybrid")
    assert result.hits
    assert not result.answerable


def test_off_topic_question_is_still_not_answerable_with_hybrid(indexed):
    assert not retrieve(indexed, "Who won the football world cup in 2022?", mode="hybrid").answerable


def test_hybrid_handles_a_question_made_only_of_stop_words(indexed):
    # No keywords left after stop words are removed: falls back to the vector results.
    assert len(search(indexed, "what is the", top_k=3, mode="hybrid")) == 3


def test_hybrid_never_returns_documents_that_are_not_ready(indexed):
    target = "office-guide-london-and-manchester.txt"
    indexed.execute("UPDATE documents SET status = 'processing' WHERE filename = %s", (target,))
    try:
        hits = search(indexed, "Is there car parking at the London office?", top_k=20, mode="hybrid")
        assert target not in {h.filename for h in hits}
    finally:
        indexed.execute("UPDATE documents SET status = 'ready' WHERE filename = %s", (target,))


def test_unknown_search_mode_is_rejected(indexed):
    with pytest.raises(ValueError, match="Unknown search mode"):
        search(indexed, "anything", mode="fuzzy")

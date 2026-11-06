"""Checks the real embedding model. The first run downloads it (about 70 MB)."""

import numpy as np

from app.config import settings
from app.ingest.embedder import embed_passages, embed_query


def test_vectors_have_the_configured_size_and_unit_length():
    [vector] = embed_passages(["Employees get 25 days of paid annual leave."])
    assert vector.shape == (settings.embedding_dim,)
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-3)


def test_a_question_is_closest_to_the_passage_that_answers_it():
    question = embed_query("How many days of holiday do I get?")
    passages = embed_passages(
        [
            "Full-time employees get 25 days of paid annual leave per year.",
            "USB storage devices are blocked on company laptops.",
            "The fire alarm is tested every Wednesday at 11:00.",
        ]
    )
    scores = [float(np.dot(question, p)) for p in passages]
    assert scores.index(max(scores)) == 0

"""Every chat question is logged once, with the right outcome, however the stream ends."""

import pytest

from app.question_log import AskedQuestion, log_questions
from tests.conftest import add_user


class FakeClock:
    """Each call moves time on by the next step (seconds)."""

    def __init__(self, *steps: float):
        self.now, self.steps = 100.0, list(steps)

    def __call__(self) -> float:
        self.now += self.steps.pop(0) if self.steps else 0
        return self.now


def _rows(db):
    return db.execute("SELECT * FROM questions ORDER BY id").fetchall()


@pytest.fixture
def asked(db):
    return AskedQuestion(add_user(db, "employee", "Sam"), "Can I deploy on Friday?", 0.71)


def _done(reason="answered", files=("eng.md",)):
    return ("done", {"answered": reason == "answered", "reason": reason, "citations": [{"filename": f} for f in files]})


def test_an_answered_question_is_logged_with_timing_and_sources(db, test_database_url, asked):
    events = [("token", {"text": "No"}), ("token", {"text": " [1]"}), _done(files=("eng.md", "eng.md", "faq.md"))]
    clock = FakeClock(0, 1.25, 2.0)  # start, first token at +1.25 s, end at +3.25 s

    passed = list(log_questions(iter(events), asked, test_database_url, clock))

    assert passed == events  # the stream is passed through untouched
    [row] = _rows(db)
    assert (row["user_name"], row["question"], row["outcome"]) == ("Sam", "Can I deploy on Friday?", "answered")
    assert row["sources"] == ["eng.md", "faq.md"]  # each file once
    assert (row["first_token_ms"], row["total_ms"]) == (1250, 3250)
    assert row["best_score"] == pytest.approx(0.71)


@pytest.mark.parametrize("reason", ["low_score", "not_in_sources", "refused"])
def test_unanswered_outcomes_are_logged(db, test_database_url, asked, reason):
    list(log_questions(iter([_done(reason, files=())]), asked, test_database_url))
    [row] = _rows(db)
    assert row["outcome"] == reason
    assert row["first_token_ms"] is None  # no text was streamed
    assert row["sources"] == []


def test_an_error_event_is_logged_as_error(db, test_database_url, asked):
    list(log_questions(iter([("error", {"message": "Ollama is down"})]), asked, test_database_url))
    assert _rows(db)[0]["outcome"] == "error"


def test_a_browser_leaving_mid_answer_is_logged_as_stopped(db, test_database_url, asked):
    stream = log_questions(
        iter([("token", {"text": "a"}), ("token", {"text": "b"}), _done()]), asked, test_database_url
    )
    next(stream)
    stream.close()  # what the server does when the client disconnects

    [row] = _rows(db)
    assert row["outcome"] == "stopped"
    assert row["first_token_ms"] is not None


def test_a_crash_inside_the_stream_is_still_logged(db, test_database_url, asked):
    def broken():
        yield ("token", {"text": "a"})
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        list(log_questions(broken(), asked, test_database_url))
    assert _rows(db)[0]["outcome"] == "stopped"


def test_a_logging_failure_never_breaks_the_answer(db, asked, caplog):
    events = [("token", {"text": "ok"}), _done()]
    passed = list(log_questions(iter(events), asked, "postgresql://nobody@127.0.0.1:1/none?connect_timeout=1"))
    assert passed == events
    assert "Could not log the question" in caplog.text

import pytest
from fastapi.testclient import TestClient

from app.api.tickets import get_ticket_drafter
from app.chat.llm import LLMError, TicketDraft
from app.deps import get_database_url
from app.main import app


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


def _use_drafter(drafter):
    app.dependency_overrides[get_ticket_drafter] = lambda: drafter


TICKET = {
    "title": "Stock options for employees",
    "question": "Do employees get stock options?",
    "summary": "Employee asks whether the company offers stock options.",
    "user_name": "Sam",
}


def test_draft_returns_the_models_tool_call(client):
    calls = []

    def drafter(question):
        calls.append(question)
        return TicketDraft(title="Stock options", summary="Asks about stock options.")

    _use_drafter(drafter)
    response = client.post("/api/tickets/draft", json={"question": "  Do employees get stock options? "})

    assert response.status_code == 200
    assert response.json() == {"title": "Stock options", "summary": "Asks about stock options.", "drafted_by": "model"}
    assert calls == ["Do employees get stock options?"]


def test_draft_falls_back_to_the_question_when_the_model_makes_no_tool_call(client):
    _use_drafter(lambda question: None)
    long_question = "Can I bring my dog to the office on Fridays if my whole team agrees that it is fine?"

    body = client.post("/api/tickets/draft", json={"question": long_question}).json()

    assert body["drafted_by"] == "fallback"
    assert body["summary"] == ""
    assert len(body["title"]) <= 80
    assert body["title"].startswith("Can I bring my dog")


def test_draft_reports_llm_errors_as_503(client):
    def drafter(question):
        raise LLMError("Could not reach the local model (Ollama). Is the ollama service running?")

    _use_drafter(drafter)
    response = client.post("/api/tickets/draft", json={"question": "Q?"})

    assert response.status_code == 503
    assert "Could not reach the local model" in response.json()["detail"]


def test_draft_saves_nothing(client):
    _use_drafter(lambda question: TicketDraft("T", "S"))
    client.post("/api/tickets/draft", json={"question": "Q?"})
    assert client.get("/api/tickets").json() == []


def test_create_then_list_newest_first(client):
    first = client.post("/api/tickets", json=TICKET)
    second = client.post("/api/tickets", json={**TICKET, "title": "Company car", "question": "Can I get a company car?"})

    assert first.status_code == 201
    assert first.json()["status"] == "open"
    listed = client.get("/api/tickets").json()
    assert [t["title"] for t in listed] == ["Company car", "Stock options for employees"]
    assert listed[1]["user_name"] == "Sam"
    assert listed[0]["id"] == second.json()["id"]


def test_summary_is_optional(client):
    response = client.post("/api/tickets", json={k: v for k, v in TICKET.items() if k != "summary"})
    assert response.status_code == 201
    assert response.json()["summary"] == ""


@pytest.mark.parametrize(
    "change",
    [{"title": "  "}, {"user_name": ""}, {"question": ""}, {"title": "x" * 121}, {"summary": "x" * 1001}],
)
def test_invalid_tickets_are_rejected(client, change):
    assert client.post("/api/tickets", json={**TICKET, **change}).status_code == 422
    assert client.get("/api/tickets").json() == []

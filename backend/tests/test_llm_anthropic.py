"""The optional Claude provider (LLM_PROVIDER=anthropic), with a fake SDK client.

No network: _anthropic_client is replaced, so these tests check what we send,
how we read the reply, and how every API failure becomes a clear LLMError.
"""

from dataclasses import replace
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.chat import llm
from app.chat.llm import LLMError, LLMRefused, TicketDraft

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeStream:
    def __init__(self, texts, stop_reason="end_turn"):
        self.text_stream = iter(texts)
        self._stop = stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop)


class FakeClient:
    """Records each call; returns the canned stream/response or raises the error."""

    def __init__(self, stream=None, response=None, error=None):
        self.calls = []
        self._stream, self._response, self._error = stream, response, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._call(lambda: self._stream)))
        self.messages = SimpleNamespace(create=self._call(lambda: self._response))

    def _call(self, result):
        def call(**kwargs):
            self.calls.append(kwargs)
            if self._error:
                raise self._error
            return result()

        return call


@pytest.fixture
def use_claude(monkeypatch):
    """Switch to the anthropic provider and install a fake client."""
    monkeypatch.setattr(llm, "settings", replace(llm.settings, llm_provider="anthropic", anthropic_api_key="test-key"))

    def install(client):
        monkeypatch.setattr(llm, "_anthropic_client", lambda: client)
        return client

    return install


def _status_error(cls, status):
    return cls("failed", response=httpx.Response(status, request=REQUEST), body=None)


# --- Answers ---------------------------------------------------------------------------


def test_streams_text_and_sends_the_configured_model_and_effort(use_claude):
    client = use_claude(FakeClient(stream=FakeStream(["Fridays ", "are out [1]."])))

    text = "".join(llm.stream_answer("SYSTEM", [{"role": "user", "content": "Can I deploy on Friday?"}]))

    assert text == "Fridays are out [1]."
    [call] = client.calls
    assert call["system"] == "SYSTEM"
    assert call["messages"] == [{"role": "user", "content": "Can I deploy on Friday?"}]
    assert call["model"] == llm.settings.answer_model
    assert call["output_config"] == {"effort": llm.settings.answer_effort}


def test_a_refusal_becomes_llm_refused(use_claude):
    use_claude(FakeClient(stream=FakeStream([], stop_reason="refusal")))
    with pytest.raises(LLMRefused):
        list(llm.stream_answer("S", [{"role": "user", "content": "x"}]))


def test_no_api_key_fails_before_calling_the_api(use_claude, monkeypatch):
    client = use_claude(FakeClient(stream=FakeStream(["never"])))
    monkeypatch.setattr(llm, "settings", replace(llm.settings, anthropic_api_key=None))
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        list(llm.stream_answer("S", [{"role": "user", "content": "x"}]))
    assert client.calls == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (_status_error(anthropic.AuthenticationError, 401), "rejected the API key"),
        (_status_error(anthropic.RateLimitError, 429), "busy"),
        (_status_error(anthropic.InternalServerError, 500), r"error \(500\)"),
        (anthropic.APIConnectionError(request=REQUEST), "Could not reach"),
        (anthropic.APITimeoutError(request=REQUEST), "Could not reach"),
    ],
)
def test_api_failures_become_clear_llm_errors(use_claude, error, message):
    use_claude(FakeClient(error=error))
    with pytest.raises(LLMError, match=message):
        list(llm.stream_answer("S", [{"role": "user", "content": "x"}]))
    with pytest.raises(LLMError, match=message):
        llm.draft_ticket("Q?")


# --- Ticket drafts ----------------------------------------------------------------------


def _response(*blocks, stop_reason="tool_use"):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def test_the_draft_comes_from_the_create_ticket_tool_call(use_claude):
    tool_use = SimpleNamespace(
        type="tool_use", name="create_ticket", input={"title": "Stock options", "summary": "Asks about equity."}
    )
    client = use_claude(FakeClient(response=_response(SimpleNamespace(type="text", text="Sure."), tool_use)))

    assert llm.draft_ticket("Do we get stock options?") == TicketDraft("Stock options", "Asks about equity.")
    [call] = client.calls
    [tool] = call["tools"]
    assert tool["name"] == "create_ticket" and tool["strict"] is True
    assert "Do we get stock options?" in call["messages"][0]["content"]


@pytest.mark.parametrize(
    "response",
    [
        _response(SimpleNamespace(type="text", text="I can't."), stop_reason="end_turn"),  # no tool call
        _response(SimpleNamespace(type="tool_use", name="other_tool", input={"title": "x"})),  # wrong tool
        _response(stop_reason="refusal"),
    ],
)
def test_no_valid_tool_call_gives_no_draft(use_claude, response):
    use_claude(FakeClient(response=response))
    assert llm.draft_ticket("Q?") is None


def test_warm_up_does_nothing_for_claude(use_claude):
    client = use_claude(FakeClient())
    assert llm.warm_up() is None
    assert client.calls == []

"""The Ollama client, against a tiny local HTTP server that speaks Ollama's protocol.

This exercises the real HTTP and line-by-line parsing code, with no mocks.
"""

import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.chat import llm
from app.chat.llm import LLMError, stream_answer, stream_ollama


class FakeOllama(BaseHTTPRequestHandler):
    status = 200
    lines: list[bytes] = []
    received: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.received.append({"path": self.path, "body": body})
        self.send_response(self.status)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for line in self.lines:
            self.wfile.write(line + b"\n")

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture
def ollama():
    FakeOllama.status, FakeOllama.lines, FakeOllama.received = 200, [], []
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield FakeOllama, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _line(content=None, done=False, **extra):
    chunk = {"done": done, **extra}
    if content is not None:
        chunk["message"] = {"role": "assistant", "content": content}
    return json.dumps(chunk).encode()


def test_streams_tokens_until_done(ollama):
    fake, url = ollama
    fake.lines = [_line("You get "), _line("25 days [1]."), _line("", done=True), _line("ignored")]

    assert "".join(stream_ollama("SYS", [{"role": "user", "content": "Q"}], base_url=url)) == "You get 25 days [1]."


def test_sends_system_prompt_first_and_low_temperature(ollama):
    fake, url = ollama
    fake.lines = [_line("ok", done=True)]

    list(stream_ollama("SYS", [{"role": "user", "content": "Q"}], base_url=url))

    [request] = fake.received
    assert request["path"] == "/api/chat"
    body = request["body"]
    assert body["stream"] is True
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "Q"}
    assert body["options"]["temperature"] <= 0.2


def test_missing_model_gives_a_clear_message(ollama):
    fake, url = ollama
    fake.status, fake.lines = 404, [json.dumps({"error": "model not found"}).encode()]

    with pytest.raises(LLMError, match="not downloaded yet"):
        list(stream_ollama("SYS", [], base_url=url))


def test_error_in_the_stream_becomes_llm_error(ollama):
    fake, url = ollama
    fake.lines = [_line("Partial"), json.dumps({"error": "out of memory"}).encode()]

    with pytest.raises(LLMError, match="out of memory"):
        list(stream_ollama("SYS", [], base_url=url))


def test_unreadable_reply_becomes_llm_error(ollama):
    fake, url = ollama
    fake.lines = [b"this is not json"]

    with pytest.raises(LLMError, match="could not read"):
        list(stream_ollama("SYS", [], base_url=url))


def test_ollama_not_running_gives_a_clear_message():
    with pytest.raises(LLMError, match="Could not reach the local model"):
        list(stream_ollama("SYS", [], base_url="http://127.0.0.1:9"))  # nothing listens on port 9


def test_anthropic_provider_without_key_gives_a_clear_message(monkeypatch):
    monkeypatch.setattr(llm, "settings", replace(llm.settings, llm_provider="anthropic", anthropic_api_key=None))

    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        list(stream_answer("SYS", []))


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(llm, "settings", replace(llm.settings, llm_provider="gpt"))

    with pytest.raises(LLMError, match="Unknown LLM_PROVIDER"):
        list(stream_answer("SYS", []))

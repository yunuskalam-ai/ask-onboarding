"""Talk to the LLM: stream answers, and draft help-desk tickets with a tool call.

This is the only file that talks to a model. Two providers, picked by
LLM_PROVIDER:

  ollama     (default) a local model in the `ollama` container. Free, no
             API key, runs on CPU. Spoken to over its HTTP API with the
             standard library, so it needs no extra package.
  anthropic  Claude through the Anthropic SDK. Needs ANTHROPIC_API_KEY.

Failures become LLMError, with a message that is safe to show users.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import anthropic

from app.config import settings


class LLMError(Exception):
    """The model call failed. The message is safe to show users."""


class LLMRefused(Exception):
    """The model's safety system declined the request (Claude's stop_reason == 'refusal')."""


class StreamAnswerFn(Protocol):
    def __call__(self, system: str, messages: list[dict]) -> Iterator[str]: ...


@dataclass(frozen=True)
class TicketDraft:
    title: str
    summary: str


class DraftTicketFn(Protocol):
    def __call__(self, question: str) -> TicketDraft | None: ...


def stream_answer(system: str, messages: list[dict]) -> Iterator[str]:
    if settings.llm_provider == "ollama":
        return stream_ollama(system, messages)
    if settings.llm_provider == "anthropic":
        return stream_anthropic(system, messages)
    raise LLMError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'ollama' or 'anthropic'.")


def draft_ticket(question: str) -> TicketDraft | None:
    """Ask the model to call create_ticket. None if it didn't make a valid call."""
    if settings.llm_provider == "ollama":
        return draft_ticket_ollama(question)
    if settings.llm_provider == "anthropic":
        return draft_ticket_anthropic(question)
    raise LLMError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'ollama' or 'anthropic'.")


# --- The ticket tool (shared by both providers) --------------------------------

TICKET_TOOL_NAME = "create_ticket"
TICKET_TOOL_DESCRIPTION = (
    "Draft a help-desk ticket for a question the company documents could not answer. "
    "A person reviews the draft before it is saved."
)
TICKET_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short ticket title, at most 80 characters."},
        "summary": {
            "type": "string",
            "description": "One or two sentences on what the employee needs to know, for the HR, IT or engineering team.",
        },
    },
    "required": ["title", "summary"],
    "additionalProperties": False,
}
TICKET_SYSTEM_PROMPT = (
    "The company documents do not answer the employee's question. "
    f"Call the {TICKET_TOOL_NAME} tool to draft a help-desk ticket for it. "
    "Do not try to answer the question yourself."
)


def parse_ticket_arguments(arguments: object) -> TicketDraft | None:
    """Validate the model's tool arguments. Model output is untrusted, so check every field."""
    if isinstance(arguments, str):  # some models send the arguments as a JSON string
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not isinstance(arguments, dict):
        return None
    title, summary = arguments.get("title"), arguments.get("summary")
    if not isinstance(title, str) or not isinstance(summary, str) or not title.strip():
        return None
    return TicketDraft(title=title.strip()[:120], summary=summary.strip()[:1000])


# --- Ollama -------------------------------------------------------------------

@contextmanager
def _ollama_errors():
    """Turn the ways an Ollama call can fail into readable LLMErrors."""
    try:
        yield
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise LLMError(
                f"The model '{settings.ollama_model}' is not downloaded yet. "
                "Wait for the ollama-pull service to finish, then try again."
            ) from exc
        raise LLMError(f"The local model returned an error ({exc.code}). Please try again.") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise LLMError("Could not reach the local model (Ollama). Is the ollama service running?") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("The local model sent a reply we could not read. Please try again.") from exc


def _ollama_request(body: dict, base_url: str | None) -> urllib.request.Request:
    return urllib.request.Request(
        f"{base_url or settings.ollama_url}/api/chat",
        data=json.dumps(
            {
                "model": settings.ollama_model,
                "keep_alive": "30m",  # keep the model in memory between questions
                "options": {
                    "temperature": 0.1,  # stay close to the sources
                    "num_ctx": 8192,  # room for 5 sources, the question and some history
                },
                **body,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )


def stream_ollama(system: str, messages: list[dict], base_url: str | None = None) -> Iterator[str]:
    """Stream from Ollama's /api/chat, which returns one JSON object per line."""
    request = _ollama_request(
        {"messages": [{"role": "system", "content": system}, *messages], "stream": True}, base_url
    )
    with _ollama_errors():
        # The timeout applies to each read, so a long answer is fine
        # as long as tokens keep arriving.
        with urllib.request.urlopen(request, timeout=120) as response:
            for line in response:
                chunk = json.loads(line)
                if "error" in chunk:
                    raise LLMError(f"The local model failed: {chunk['error']}")
                if text := chunk.get("message", {}).get("content"):
                    yield text
                if chunk.get("done"):
                    return


def draft_ticket_ollama(question: str, base_url: str | None = None) -> TicketDraft | None:
    request = _ollama_request(
        {
            "messages": [
                {"role": "system", "content": TICKET_SYSTEM_PROMPT},
                {"role": "user", "content": f"Employee question: {question}"},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": TICKET_TOOL_NAME,
                        "description": TICKET_TOOL_DESCRIPTION,
                        "parameters": TICKET_TOOL_SCHEMA,
                    },
                }
            ],
            "stream": False,
        },
        base_url,
    )
    with _ollama_errors():
        with urllib.request.urlopen(request, timeout=180) as response:
            reply = json.load(response)
    for call in reply.get("message", {}).get("tool_calls") or []:
        function = call.get("function", {})
        if function.get("name") == TICKET_TOOL_NAME:
            return parse_ticket_arguments(function.get("arguments"))
    return None


# --- Anthropic ----------------------------------------------------------------

@lru_cache(maxsize=1)
def _anthropic_client() -> anthropic.Anthropic:
    # Retries 429, 5xx and connection errors twice with backoff.
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)


@contextmanager
def _anthropic_errors():
    if not settings.anthropic_api_key:
        raise LLMError("LLM_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is not set.")
    try:
        yield
    except anthropic.AuthenticationError as exc:
        raise LLMError("The AI service rejected the API key. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("The AI service is busy. Please try again in a minute.") from exc
    except anthropic.APIConnectionError as exc:  # includes timeouts
        raise LLMError("Could not reach the AI service. Please try again.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"The AI service returned an error ({exc.status_code}). Please try again.") from exc


def stream_anthropic(system: str, messages: list[dict]) -> Iterator[str]:
    """Stream from Claude. Raises LLMRefused if the model declines."""
    with _anthropic_errors():
        with _anthropic_client().beta.messages.stream(
            model=settings.answer_model,
            max_tokens=8000,
            system=system,
            messages=messages,
            # Short grounded answers: low effort keeps the first token fast.
            output_config={"effort": settings.answer_effort},
            # If a safety classifier declines, the API retries on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
    if final.stop_reason == "refusal":
        raise LLMRefused()


def draft_ticket_anthropic(question: str) -> TicketDraft | None:
    with _anthropic_errors():
        response = _anthropic_client().messages.create(
            model=settings.answer_model,
            max_tokens=4000,
            system=TICKET_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Employee question: {question}"}],
            # Current Claude models don't allow forcing a tool, so the prompt asks
            # for it and strict mode guarantees schema-valid arguments.
            tools=[
                {
                    "name": TICKET_TOOL_NAME,
                    "description": TICKET_TOOL_DESCRIPTION,
                    "input_schema": TICKET_TOOL_SCHEMA,
                    "strict": True,
                }
            ],
            output_config={"effort": settings.answer_effort},
        )
    if response.stop_reason == "refusal":
        return None
    for block in response.content:
        if block.type == "tool_use" and block.name == TICKET_TOOL_NAME:
            return parse_ticket_arguments(block.input)
    return None

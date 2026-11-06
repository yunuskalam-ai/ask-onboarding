"""Stream an answer from the LLM.

This is the only file that talks to a model. Two providers, picked by
LLM_PROVIDER:

  ollama     (default) a local model in the `ollama` container. Free, no
             API key, runs on CPU. Spoken to over its HTTP API with the
             standard library, so it needs no extra package.
  anthropic  Claude through the Anthropic SDK. Needs ANTHROPIC_API_KEY.

Both yield the answer's text as it is generated, and both turn failures
into LLMError with a message that is safe to show users.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from functools import lru_cache
from typing import Protocol

import anthropic

from app.config import settings


class LLMError(Exception):
    """The answer could not be generated. The message is safe to show users."""


class LLMRefused(Exception):
    """The model's safety system declined the request (Claude's stop_reason == 'refusal')."""


class StreamAnswerFn(Protocol):
    def __call__(self, system: str, messages: list[dict]) -> Iterator[str]: ...


def stream_answer(system: str, messages: list[dict]) -> Iterator[str]:
    if settings.llm_provider == "ollama":
        return stream_ollama(system, messages)
    if settings.llm_provider == "anthropic":
        return stream_anthropic(system, messages)
    raise LLMError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'ollama' or 'anthropic'.")


# --- Ollama -------------------------------------------------------------------

def stream_ollama(system: str, messages: list[dict], base_url: str | None = None) -> Iterator[str]:
    """Stream from Ollama's /api/chat, which returns one JSON object per line."""
    request = urllib.request.Request(
        f"{base_url or settings.ollama_url}/api/chat",
        data=json.dumps(
            {
                "model": settings.ollama_model,
                "messages": [{"role": "system", "content": system}, *messages],
                "stream": True,
                "keep_alive": "30m",  # keep the model in memory between questions
                "options": {
                    "temperature": 0.1,  # grounded answers: stay close to the sources
                    "num_ctx": 8192,  # room for 5 sources, the question and some history
                },
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
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


# --- Anthropic ----------------------------------------------------------------

@lru_cache(maxsize=1)
def _anthropic_client() -> anthropic.Anthropic:
    # Retries 429, 5xx and connection errors twice with backoff.
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)


def stream_anthropic(system: str, messages: list[dict]) -> Iterator[str]:
    """Stream from Claude. Raises LLMRefused if the model declines."""
    if not settings.anthropic_api_key:
        raise LLMError("LLM_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is not set.")

    try:
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
    except anthropic.AuthenticationError as exc:
        raise LLMError("The AI service rejected the API key. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("The AI service is busy. Please try again in a minute.") from exc
    except anthropic.APIConnectionError as exc:  # includes timeouts
        raise LLMError("Could not reach the AI service. Please try again.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"The AI service returned an error ({exc.status_code}). Please try again.") from exc

    if final.stop_reason == "refusal":
        raise LLMRefused()

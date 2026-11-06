"""Stream an answer from Claude.

This is the only file that talks to the Anthropic API. Swapping to another
provider means rewriting stream_answer() and nothing else.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Protocol

import anthropic

from app.config import settings


class LLMError(Exception):
    """The answer could not be generated. The message is safe to show users."""


class LLMRefused(Exception):
    """The model's safety system declined the request (stop_reason == 'refusal')."""


class StreamAnswerFn(Protocol):
    def __call__(self, system: str, messages: list[dict]) -> Iterator[str]: ...


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    # Retries 429, 5xx and connection errors twice with backoff.
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)


def stream_answer(system: str, messages: list[dict]) -> Iterator[str]:
    """Yield the answer's text as it is generated.

    Raises LLMRefused if the model declines, LLMError for any API failure.
    """
    if not settings.anthropic_api_key:
        raise LLMError("The server has no ANTHROPIC_API_KEY. Add it to .env and restart.")

    try:
        with _client().beta.messages.stream(
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

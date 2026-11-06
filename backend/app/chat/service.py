"""Turn a question into a stream of events: tokens, then a final summary.

Events are (name, data) pairs, sent to the browser as Server-Sent Events:
  token  {"text": "..."}                     part of the answer, in order
  done   {"answered": bool, "reason": ...,   once, at the end
          "citations": [...]}
  error  {"message": "..."}                  instead of done, if the LLM failed

reason is one of:
  "answered"        - a grounded answer with citations
  "low_score"       - retrieval found nothing relevant; the LLM was not called
  "not_in_sources"  - the LLM read the sources and used the refusal sentence
  "refused"         - the model's safety system declined; show NO_ANSWER instead
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from app.chat.llm import LLMError, LLMRefused, StreamAnswerFn, stream_answer
from app.chat.prompt import NO_ANSWER, SYSTEM_PROMPT, build_user_message, cited_hits, is_no_answer, strip_citations
from app.retrieval.search import Retrieval

MAX_HISTORY_TURNS = 6  # older turns are dropped to keep the prompt small

Event = tuple[str, dict]


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str


def answer_events(
    question: str,
    retrieval: Retrieval,
    history: list[Turn] | None = None,
    llm: StreamAnswerFn = stream_answer,
) -> Iterator[Event]:
    if not retrieval.answerable:
        yield "token", {"text": NO_ANSWER}
        yield "done", {"answered": False, "reason": "low_score", "citations": []}
        return

    messages = _history_messages(history or [])
    messages.append({"role": "user", "content": build_user_message(question, retrieval.hits)})

    parts: list[str] = []
    try:
        for text in llm(SYSTEM_PROMPT, messages):
            parts.append(text)
            yield "token", {"text": text}
    except LLMRefused:
        # Any partial text is discarded by the client; it shows NO_ANSWER instead.
        yield "done", {"answered": False, "reason": "refused", "citations": []}
        return
    except LLMError as exc:
        yield "error", {"message": str(exc)}
        return

    answer = "".join(parts)
    if is_no_answer(answer):
        yield "done", {"answered": False, "reason": "not_in_sources", "citations": []}
        return

    citations = [
        {
            "n": n,
            "document_id": hit.document_id,
            "filename": hit.filename,
            "page": hit.page,
            "start_char": hit.start_char,
            "end_char": hit.end_char,
            "text": hit.text,
        }
        for n, hit in cited_hits(answer, retrieval.hits)
    ]
    yield "done", {"answered": True, "reason": "answered", "citations": citations}


def _history_messages(history: list[Turn]) -> list[dict]:
    """Earlier turns as plain text. The API needs the first message to be from the user."""
    recent = history[-MAX_HISTORY_TURNS:]
    while recent and recent[0].role != "user":
        recent = recent[1:]
    return [
        {"role": t.role, "content": strip_citations(t.content) if t.role == "assistant" else t.content}
        for t in recent
        if t.content.strip()
    ]

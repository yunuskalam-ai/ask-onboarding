"""Split page text into overlapping chunks with exact character offsets.

Sizes are in characters, not tokens: no tokenizer dependency, and the
offsets we store are the same unit we use to highlight the passage.
About 4 characters make one English token, so 800 characters is roughly
200 tokens.

Rules:
- A chunk never crosses a page boundary, so every chunk has one page.
- A chunk prefers to end at a paragraph break, then a line or sentence
  end, then a space. It only cuts mid-word if a word is longer than `size`.
- Neighbouring chunks share about `overlap` characters, so a fact that
  sits on a boundary is still whole in at least one chunk.
- page_text[start_char:end_char] == chunk.text, always.
"""

from dataclasses import dataclass

from app.ingest.parsers import Page

# Break points, best first. A chunk ends just after the separator.
_SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class Chunk:
    index: int  # position in the whole document, 0-based
    page: int | None
    start_char: int  # offset into that page's text
    end_char: int
    text: str


def chunk_pages(pages: list[Page], size: int = 800, overlap: int = 100) -> list[Chunk]:
    """Chunk every page of a document, numbering chunks across the document."""
    chunks: list[Chunk] = []
    for page in pages:
        for start, end in chunk_spans(page.text, size, overlap):
            chunks.append(Chunk(len(chunks), page.number, start, end, page.text[start:end]))
    return chunks


def chunk_spans(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """Return (start, end) offsets of each chunk in `text`."""
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size // 2:
        raise ValueError("overlap must be at least 0 and less than half of size")

    spans: list[tuple[int, int]] = []
    start = _skip_whitespace(text, 0)
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            end = _best_break(text, start, end, size)

        trimmed_end = end
        while trimmed_end > start and text[trimmed_end - 1].isspace():
            trimmed_end -= 1
        spans.append((start, trimmed_end))

        if end >= len(text):
            break
        # Step back by `overlap`, then forward to the start of a word,
        # so the next chunk does not begin halfway through a word.
        next_start = _next_word_start(text, max(end - overlap, start + 1), end)
        start = _skip_whitespace(text, next_start)
    return spans


def _best_break(text: str, start: int, end: int, size: int) -> int:
    # Only look in the second half of the window, so chunks never get tiny.
    earliest = start + size // 2
    for separator in _SEPARATORS:
        position = text.rfind(separator, earliest, end)
        if position != -1:
            return position + len(separator)
    return end  # one very long word: cut it


def _next_word_start(text: str, position: int, limit: int) -> int:
    while position < limit and not text[position - 1].isspace():
        position += 1
    return position


def _skip_whitespace(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position

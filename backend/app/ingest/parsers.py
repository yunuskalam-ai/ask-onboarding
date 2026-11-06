"""Turn an uploaded file into plain text, split into pages.

PDFs keep one Page per PDF page, so a citation can open the right page.
Markdown and text files become a single Page with page=None.
Markdown is kept as written (not converted to HTML), so the character
offsets we store point into the same text we show in the source panel.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PdfReadError

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


class UnsupportedFileType(ValueError):
    """The file extension is not one we can ingest."""


class EmptyDocument(ValueError):
    """The file has no text we can extract (for example, a scanned PDF)."""


@dataclass(frozen=True)
class Page:
    number: int | None  # 1-based PDF page number, or None for MD/TXT
    text: str


def file_type(filename: str) -> str:
    """Return the normalised type ('pdf', 'md' or 'txt'), or raise UnsupportedFileType."""
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileType(f"'{filename}' is not supported. Allowed types: {allowed}.")
    return {".pdf": "pdf", ".md": "md", ".markdown": "md", ".txt": "txt"}[ext]


def parse(filename: str, data: bytes) -> list[Page]:
    """Extract text pages from a file's bytes."""
    kind = file_type(filename)
    pages = _parse_pdf(data) if kind == "pdf" else [Page(None, _decode_text(data))]

    if not any(page.text.strip() for page in pages):
        raise EmptyDocument(f"'{filename}' has no extractable text.")
    return pages


def _parse_pdf(data: bytes) -> list[Page]:
    try:
        reader = PdfReader(BytesIO(data))
        return [
            Page(number, _normalise_newlines(page.extract_text() or ""))
            for number, page in enumerate(reader.pages, start=1)
        ]
    except PdfReadError as exc:
        raise EmptyDocument(f"Could not read PDF: {exc}") from exc


def _decode_text(data: bytes) -> str:
    # utf-8-sig also strips a byte-order mark if an editor added one.
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Older Windows tools save text as cp1252; this never fails.
        text = data.decode("cp1252", errors="replace")
    return _normalise_newlines(text)


def _normalise_newlines(text: str) -> str:
    # Windows line endings would shift every offset after them by one.
    return text.replace("\r\n", "\n").replace("\r", "\n")

"""The project's own documentation, for admins to read in the app.

Only the documents listed in DOCS can be read, and only image files directly
inside docs/: names are looked up in a fixed table or checked against a strict
pattern, never joined into a path from user input, so nothing else on the
server can be reached (no path traversal).
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.deps import Admin

router = APIRouter(prefix="/api/admin/docs", tags=["admin"])

# slug -> (title, path from the repo root). The order is the reading order.
DOCS: dict[str, tuple[str, str]] = {
    "guide": ("Guide (plain language)", "GUIDE.md"),
    "readme": ("README", "README.md"),
    "architecture": ("Architecture", "ARCHITECTURE.md"),
    "technical": ("Technical reference", "TECHNICAL.md"),
    "testing": ("Testing", "TESTING.md"),
    "deploy": ("Deploying", "deploy/README.md"),
    "ai-log": ("AI log", "AI_LOG.md"),
}

_ASSET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*\.(png|svg)$")
_MEDIA_TYPES = {"png": "image/png", "svg": "image/svg+xml"}


class DocSummary(BaseModel):
    slug: str
    title: str
    path: str
    available: bool


class Doc(BaseModel):
    slug: str
    title: str
    path: str  # where it lives in the repo, for links to GitHub
    markdown: str


def _file(relative: str) -> Path:
    return Path(settings.project_dir) / relative


@router.get("")
def list_docs(admin: Admin) -> list[DocSummary]:
    return [
        DocSummary(slug=slug, title=title, path=path, available=_file(path).is_file())
        for slug, (title, path) in DOCS.items()
    ]


@router.get("/assets/{name}")
def doc_asset(name: str, admin: Admin) -> FileResponse:
    """An image used by the docs (docs/*.png, docs/*.svg)."""
    match = _ASSET_NAME.fullmatch(name)
    path = _file("docs") / name
    if not match or not path.is_file():
        raise HTTPException(404, "No such image.")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[match.group(1)],
        headers={
            "X-Content-Type-Options": "nosniff",
            # An SVG is a document that could carry script: never let it run as one.
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{slug}")
def read_doc(slug: str, admin: Admin) -> Doc:
    if slug not in DOCS:
        raise HTTPException(404, "No such document.")
    title, path = DOCS[slug]
    file = _file(path)
    if not file.is_file():
        raise HTTPException(404, f"{path} is not available on this server.")
    return Doc(slug=slug, title=title, path=path, markdown=file.read_text(encoding="utf-8"))

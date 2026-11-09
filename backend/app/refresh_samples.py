"""Replace stored sample documents with the current files in sample_docs/.

Use it after the sample documents change (for example when the demo company
was renamed). For each file in sample_docs/ that is already in the library
under the same name with different content, the stored copy is replaced and
re-indexed, exactly like re-uploading it. Unchanged files, files not in the
library, and documents with other names are left alone. Safe to run again.

    docker compose exec api python -m app.refresh_samples
"""

from pathlib import Path

from app.config import settings
from app.db import connect
from app.ingest.embedder import embed_passages
from app.ingest.parsers import SUPPORTED_EXTENSIONS
from app.ingest.service import EmbedFn, process_document, save_upload


def refresh_samples(
    database_url: str | None = None, folder: Path | None = None, embed: EmbedFn = embed_passages
) -> list[str]:
    """Returns the names of the documents that were replaced."""
    folder = folder or Path(settings.sample_docs_dir)
    replaced = []
    with connect(database_url) as conn:
        stored = {r["filename"] for r in conn.execute("SELECT filename FROM documents")}
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS or path.name not in stored:
                continue
            upload = save_upload(conn, path.name, path.read_bytes())
            if upload.unchanged:
                continue
            process_document(conn, upload.document_id, embed)
            replaced.append(path.name)
    return replaced


def main() -> None:
    replaced = refresh_samples()
    print(f"Replaced {len(replaced)} sample documents" + (": " + ", ".join(replaced) if replaced else "."))


if __name__ == "__main__":
    main()

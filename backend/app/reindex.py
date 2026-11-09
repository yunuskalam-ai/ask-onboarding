"""Re-chunk and re-embed every stored document with the current settings.

Use it after changing CHUNK_SIZE, CHUNK_OVERLAP or EMBEDDING_MODEL:
re-uploading the same files would do nothing, because identical files are
skipped. Each document is rebuilt from its stored original, so nothing is
lost, and each one is swapped in its own transaction.

    docker compose exec api python -m app.reindex
"""

from app.config import settings
from app.db import connect, one
from app.ingest.embedder import embed_passages
from app.ingest.service import EmbedFn, process_document


def main(database_url: str | None = None, embed: EmbedFn = embed_passages) -> None:
    with connect(database_url) as conn:
        docs = conn.execute("SELECT id, filename FROM documents ORDER BY id").fetchall()
        print(f"Re-indexing {len(docs)} documents (chunk size {settings.chunk_size}, overlap {settings.chunk_overlap})")
        for doc in docs:
            process_document(conn, doc["id"], embed)
            row = one(
                conn.execute(
                    "SELECT d.status, (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS n "
                    "FROM documents d WHERE d.id = %s",
                    (doc["id"],),
                )
            )
            print(f"  {row['status']:6} {row['n']:3} chunks  {doc['filename']}")


if __name__ == "__main__":
    main()

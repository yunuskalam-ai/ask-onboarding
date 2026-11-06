import { useEffect, useRef, useState } from "react";
import { ApiError, documentFileUrl, getDocumentText, type Citation, type DocumentText } from "../api";

type Props = { citation: Citation; onClose: () => void };

// Loaded documents, so clicking between citations doesn't refetch.
const cache = new Map<number, DocumentText>();

/**
 * Shows the cited document with the exact passage highlighted.
 * The parent renders it with key={document_id}, so switching to another
 * document starts with fresh state.
 */
export default function SourcePanel({ citation, onClose }: Props) {
  const [doc, setDoc] = useState<DocumentText | null>(() => cache.get(citation.document_id) ?? null);
  const [error, setError] = useState<string | null>(null);
  const mark = useRef<HTMLElement>(null);

  useEffect(() => {
    if (cache.has(citation.document_id)) return;
    let cancelled = false;
    getDocumentText(citation.document_id)
      .then((d) => {
        cache.set(d.id, d);
        if (!cancelled) setDoc(d);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the document.");
      });
    return () => {
      cancelled = true;
    };
  }, [citation.document_id]);

  useEffect(() => {
    mark.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [doc, citation]);

  const page = doc?.pages.find((p) => p.number === citation.page);
  // The stored text can differ if the document was re-uploaded after this answer.
  const stale = page && page.text.slice(citation.start_char, citation.end_char) !== citation.text;

  return (
    <aside className="source-panel" aria-label="Source">
      <header>
        <div>
          <strong>[{citation.n}] {citation.filename}</strong>
          {citation.page && <span className="muted"> · page {citation.page}</span>}
        </div>
        <button className="link" onClick={onClose} aria-label="Close source">
          ✕
        </button>
      </header>

      <a className="open-file" href={documentFileUrl(citation.document_id, citation.page)} target="_blank" rel="noreferrer">
        {citation.page ? `Open PDF at page ${citation.page}` : "Open original file"}
      </a>

      <div className="source-body">
        {error && <p className="notice error">{error}</p>}
        {!doc && !error && <p className="muted">Loading document…</p>}
        {doc && !page && <p className="notice error">This page is no longer in the document.</p>}
        {page && stale && (
          <>
            <p className="notice">The document changed since this answer. The cited passage was:</p>
            <mark ref={mark}>{citation.text}</mark>
          </>
        )}
        {page && !stale && (
          <pre>
            {page.text.slice(0, citation.start_char)}
            <mark ref={mark}>{page.text.slice(citation.start_char, citation.end_char)}</mark>
            {page.text.slice(citation.end_char)}
          </pre>
        )}
      </div>
    </aside>
  );
}

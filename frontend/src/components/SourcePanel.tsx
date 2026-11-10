import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApiError, documentFileUrl, getDocumentText, type Citation, type DocumentText } from "../api";
import { markPassage, rehypeCitedPassage } from "../citedPassage";

type Props = { citation: Citation; onClose: () => void };

// Loaded documents, so clicking between citations doesn't refetch.
const cache = new Map<number, DocumentText>();

/**
 * Shows the cited document with the exact passage highlighted. Markdown is
 * shown formatted, with the passage's paragraphs marked; text files and PDFs
 * as text. The parent renders it with key={document_id}, so switching to
 * another document starts with fresh state.
 */
export default function SourcePanel({ citation, onClose }: Props) {
  const [doc, setDoc] = useState<DocumentText | null>(() => cache.get(citation.document_id) ?? null);
  const [error, setError] = useState<string | null>(null);
  const body = useRef<HTMLDivElement>(null);

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

  // Bring the start of the cited passage into view.
  useEffect(() => {
    body.current?.querySelector("mark")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [doc, citation]);

  const page = doc?.pages.find((p) => p.number === citation.page);
  // The stored text can differ if the document was re-uploaded after this answer.
  const stale = page && page.text.slice(citation.start_char, citation.end_char) !== citation.text;

  return (
    <aside className="source-panel" aria-label="Source">
      <header>
        <div className="source-heading">
          <span className="source-n">{citation.n}</span>
          <span>
            <strong>{citation.title}</strong>
            <span className="muted small">
              {" "}
              {citation.filename}
              {citation.page ? ` · page ${citation.page}` : ""}
            </span>
          </span>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close source">
          ✕
        </button>
      </header>

      <div className="source-body" ref={body}>
        {error && <p className="notice error">{error}</p>}
        {!doc && !error && <p className="muted">Loading document…</p>}
        {doc && !page && <p className="notice error">This page is no longer in the document.</p>}
        {page && stale && (
          <>
            <p className="notice">The document changed since this answer. The cited passage was:</p>
            <p className="cited">
              <mark>{citation.text}</mark>
            </p>
          </>
        )}
        {page && !stale && doc?.file_type === "md" && (
          <div className="doc-markdown">
            <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeCitedPassage]}>
              {markPassage(page.text, citation.start_char, citation.end_char)}
            </Markdown>
          </div>
        )}
        {page && !stale && doc?.file_type !== "md" && (
          <pre className="doc-text">
            {page.text.slice(0, citation.start_char)}
            <mark>{page.text.slice(citation.start_char, citation.end_char)}</mark>
            {page.text.slice(citation.end_char)}
          </pre>
        )}
      </div>

      <footer className="source-footer">
        <a href={documentFileUrl(citation.document_id, citation.page)} target="_blank" rel="noreferrer">
          {citation.page ? `Open the PDF at page ${citation.page}` : "Open the original file"}
        </a>
      </footer>
    </aside>
  );
}

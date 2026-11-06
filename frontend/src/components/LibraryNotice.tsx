import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listDocuments, type DocumentInfo } from "../api";

const POLL_MS = 3000;

/**
 * Explains empty answers before they happen: no documents yet, or some
 * still processing (for example while the samples load on first start).
 */
export default function LibraryNotice() {
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);

  const processing = docs?.filter((d) => d.status === "processing").length ?? 0;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const all = await listDocuments();
        if (cancelled) return;
        setDocs(all);
        if (all.some((d) => d.status === "processing")) timer = setTimeout(load, POLL_MS);
      } catch {
        // The chat shows its own errors; this notice is only a hint.
      }
    }
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  if (docs === null) return null;
  const ready = docs.filter((d) => d.status === "ready").length;

  if (ready === 0 && processing === 0)
    return (
      <div className="notice">
        No documents yet, so there is nothing to answer from. <Link to="/documents">Upload some documents</Link>.
      </div>
    );
  if (processing > 0)
    return (
      <div className="notice">
        {processing} document{processing === 1 ? " is" : "s are"} still being processed. Answers can only use the{" "}
        {ready} that {ready === 1 ? "is" : "are"} ready.
      </div>
    );
  return null;
}

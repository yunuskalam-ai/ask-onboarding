import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getLibrarySummary } from "../api";
import { isAdmin, useAuth } from "../session";

const POLL_MS = 3000;

/**
 * Explains empty answers before they happen: no documents yet, or some
 * still processing (for example while the samples load on first start).
 */
export default function LibraryNotice() {
  const { user } = useAuth();
  const [counts, setCounts] = useState<{ ready: number; processing: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const summary = await getLibrarySummary();
        if (cancelled) return;
        setCounts(summary);
        if (summary.processing > 0) timer = setTimeout(load, POLL_MS);
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

  if (counts === null) return null;
  const { ready, processing } = counts;

  if (ready === 0 && processing === 0)
    return (
      <div className="notice">
        No documents yet, so there is nothing to answer from.{" "}
        {isAdmin(user) ? <Link to="/documents">Upload some documents</Link> : "Ask an admin to add some."}
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

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getAlert, type AlertDetails } from "../api";
import HealthChecks from "../components/HealthChecks";
import { timeAgo } from "../timeAgo";

const REFRESH_MS = 15_000;
const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" });
const SEVERITY_LABEL = { error: "Error", warning: "Warning", info: "Info" } as const;

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (for example over plain http): the command can still be selected.
    }
  }
  return (
    <button className="copy" onClick={copy} aria-label="Copy command">
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** Admins: one system alert: what it means, how to fix it, and whether it has recovered (checked live). */
export default function AlertPage() {
  const { id } = useParams();
  const [alert, setAlert] = useState<AlertDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [checking, setChecking] = useState(false);

  const show = useCallback((details: AlertDetails) => {
    setAlert(details);
    setCheckedAt(new Date());
    setError(null);
  }, []);
  const fail = useCallback((err: unknown) => {
    setError(err instanceof ApiError ? err.message : "Could not load the alert.");
  }, []);

  // Load now, then re-run the live checks every 15 seconds while the page is visible.
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      getAlert(Number(id))
        .then((d) => !cancelled && show(d))
        .catch((err) => !cancelled && fail(err));
    };
    refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [id, show, fail]);

  async function checkNow() {
    setChecking(true);
    try {
      show(await getAlert(Number(id)));
    } catch (err) {
      fail(err);
    } finally {
      setChecking(false);
    }
  }

  if (error)
    return (
      <section className="page">
        <div className="notice error">{error}</div>
      </section>
    );
  if (!alert) return <p className="page muted">Loading…</p>;

  return (
    <section className="page alert-page">
      <p className="small">
        <Link to="/overview">← Overview</Link>
      </p>
      <div className="alert-head">
        <span className={`severity ${alert.severity}`}>{SEVERITY_LABEL[alert.severity]}</span>
        <h1>{alert.title}</h1>
      </div>
      <p className="muted">
        First seen {when.format(new Date(alert.first_seen))}
        {alert.occurrences > 1 && (
          <>
            {" "}
            · happened <strong>{alert.occurrences} times</strong>, most recently {timeAgo(alert.last_seen)}
          </>
        )}
      </p>
      {alert.body && <blockquote className="alert-message">{alert.body}</blockquote>}

      <div className={`panel status-panel ${alert.recovered ? "recovered" : "failing"}`}>
        <div className="status-head">
          <h2>{alert.recovered ? "Recovered: these checks pass now" : "Still failing"}</h2>
          <button className="link" onClick={checkNow} disabled={checking}>
            {checking ? "Checking…" : "Check again"}
          </button>
        </div>
        <HealthChecks checks={alert.checks} />
        {checkedAt && <p className="muted small">Checked live at {checkedAt.toLocaleTimeString()}. Re-checks every 15 seconds.</p>}
      </div>

      <div className="panel">
        <h2>What this means</h2>
        <p>{alert.meaning}</p>
        <h2 className="spaced">Likely causes</h2>
        <ul>
          {alert.causes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>

      <div className="panel">
        <h2>How to fix it</h2>
        <p className="muted small">
          Commands are for the Docker Compose stack. On the deployed server, run them in <code>~/ask-onboarding</code>{" "}
          with <code>sudo</code> in front.
        </p>
        <ol className="fix-steps">
          {alert.steps.map((s) => (
            <li key={s.text}>
              <p>{s.text}</p>
              {s.command && (
                <div className="command">
                  <code>{s.command}</code>
                  <CopyButton text={s.command} />
                </div>
              )}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

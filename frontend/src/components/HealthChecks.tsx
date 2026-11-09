import type { HealthCheck } from "../api";

const LABEL: Record<HealthCheck["name"], string> = { database: "Database", model: "Answer model", documents: "Documents" };

/** A row of live checks: a tick or a cross, a plain sentence and the numbers. */
export default function HealthChecks({ checks }: { checks: HealthCheck[] }) {
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.name} className={c.ok ? "ok" : "bad"}>
          <span className="check-mark" aria-hidden="true">
            {c.ok ? "✓" : "✕"}
          </span>
          <span>
            <strong>{LABEL[c.name]}:</strong> {c.summary}
            {c.detail && <span className="muted small"> ({c.detail})</span>}
            <span className="sr-only">{c.ok ? " Working." : " Failing."}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

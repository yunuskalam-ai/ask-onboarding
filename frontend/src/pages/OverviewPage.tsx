import { useEffect, useState } from "react";
import {
  ApiError,
  getOverview,
  listAudit,
  listQuestions,
  type AuditEntry,
  type LoggedQuestion,
  type Overview,
} from "../api";
import { OUTCOME_LABEL, OUTCOME_ORDER, count, describeAudit, hours, localDate, percent, seconds } from "../overviewFormat";

const PERIODS = [7, 30, 90];
const PAGE = 25;
const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const dayLabel = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" });

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="tile">
      <span className="tile-label">{label}</span>
      <strong className="tile-value">{value}</strong>
      {note && <span className="tile-note">{note}</span>}
    </div>
  );
}

/** Questions per day as stacked bars: answered (bottom) and not answered. */
function QuestionsChart({ days }: { days: Overview["questions"]["per_day"] }) {
  const [focus, setFocus] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.total));
  const W = 600;
  const H = 140;
  const step = W / days.length;
  const bar = Math.max(2, step - 2); // a 2px surface gap between neighbouring bars
  const y = (n: number) => (n / max) * H;
  const shown = focus === null ? null : days[focus];

  return (
    <figure className="chart">
      <div className="chart-head">
        <ul className="legend" aria-label="Legend">
          <li>
            <span className="swatch answered" aria-hidden="true" /> Answered from the documents
          </li>
          <li>
            <span className="swatch unanswered" aria-hidden="true" /> Not answered
          </li>
        </ul>
        <span className="readout" aria-live="polite">
          {shown
            ? `${dayLabel.format(localDate(shown.day))}: ${shown.total} asked, ${shown.answered} answered`
            : `Most in a day: ${max}`}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Questions per day">
        {days.map((d, i) => {
          const answeredH = y(d.answered);
          const otherH = y(d.total - d.answered);
          const x = i * step + (step - bar) / 2;
          return (
            <g
              key={d.day}
              className={focus === i ? "bar on" : "bar"}
              onMouseEnter={() => setFocus(i)}
              onMouseLeave={() => setFocus(null)}
            >
              {/* A full-height, invisible hit target: easier to hover than a thin bar. */}
              <rect x={i * step} y={0} width={step} height={H} className="hit" />
              {answeredH > 0 && <rect x={x} y={H - answeredH} width={bar} height={answeredH} className="answered" rx={2} />}
              {otherH > 0 && (
                // 2px surface gap between the stacked segments
                <rect
                  x={x}
                  y={H - answeredH - otherH}
                  width={bar}
                  height={Math.max(0, otherH - (answeredH > 0 ? 2 : 0))}
                  className="unanswered"
                  rx={2}
                />
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="muted small">
        {dayLabel.format(localDate(days[0].day))} to {dayLabel.format(localDate(days[days.length - 1].day))}
      </figcaption>
      <details>
        <summary className="small">Show as a table</summary>
        <table className="docs compact">
          <thead>
            <tr>
              <th>Day</th>
              <th className="num">Asked</th>
              <th className="num">Answered</th>
            </tr>
          </thead>
          <tbody>
            {days
              .filter((d) => d.total > 0)
              .map((d) => (
                <tr key={d.day}>
                  <td>{dayLabel.format(localDate(d.day))}</td>
                  <td className="num">{d.total}</td>
                  <td className="num">{d.answered}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

/** A labelled count with a thin bar for its share of the total. */
function ShareRows({ rows }: { rows: { label: string; count: number }[] }) {
  const total = rows.reduce((sum, r) => sum + r.count, 0);
  return (
    <ul className="shares">
      {rows.map((r) => (
        <li key={r.label}>
          <span>{r.label}</span>
          <span className="share-count">{r.count}</span>
          <span className="share-track" aria-hidden="true">
            {/* Set through the DOM style API, which the CSP allows (unlike a style="" attribute in HTML). */}
            <span className="share-fill" style={{ width: `${total ? (r.count / total) * 100 : 0}%` }} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function usePaged<T>(load: (limit: number, offset: number) => Promise<T[]>) {
  const [items, setItems] = useState<T[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchPage(offset: number) {
    try {
      const page = await load(PAGE, offset);
      setItems((prev) => (offset === 0 ? page : [...(prev ?? []), ...page]));
      setMore(page.length === PAGE);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load.");
    }
  }

  // First page on mount. `load` is a module-level API function, so it never changes.
  useEffect(() => {
    let cancelled = false;
    load(PAGE, 0)
      .then((page) => !cancelled && (setItems(page), setMore(page.length === PAGE)))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : "Could not load."));
    return () => {
      cancelled = true;
    };
  }, [load]);
  return { items, more, error, loadMore: () => fetchPage(items?.length ?? 0) };
}

export default function OverviewPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const questions = usePaged<LoggedQuestion>(listQuestions);
  const audit = usePaged<AuditEntry>(listAudit);

  useEffect(() => {
    let cancelled = false;
    getOverview(days, Intl.DateTimeFormat().resolvedOptions().timeZone)
      .then((d) => !cancelled && (setData(d), setError(null)))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : "Could not load the overview."));
    return () => {
      cancelled = true;
    };
  }, [days]);

  const q = data?.questions;
  const openTickets = data ? data.tickets.by_status.open + data.tickets.by_status.in_progress : 0;

  return (
    <section className="page wide">
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p className="muted">How the assistant is doing, what employees ask that the documents miss, and who did what.</p>
        </div>
        <div className="filters" role="tablist" aria-label="Period">
          {PERIODS.map((p) => (
            <button key={p} role="tab" aria-selected={days === p} className={days === p ? "on" : ""} onClick={() => setDays(p)}>
              Last {p} days
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {!data && !error && <p className="muted">Loading…</p>}

      {data && q && (
        <>
          <div className="tiles">
            <Tile label="Questions asked" value={String(q.total)} note={`in the last ${data.days} days`} />
            <Tile label="Answered from the documents" value={percent(q.answer_rate)} note={`${q.answered} of ${q.total}`} />
            <Tile
              label="Time to first word"
              value={seconds(q.median_first_token_ms)}
              note={q.p90_first_token_ms === null ? "median" : `median · 9 in 10 within ${seconds(q.p90_first_token_ms)}`}
            />
            <Tile
              label="Open tickets"
              value={String(openTickets)}
              note={`median ${hours(data.tickets.median_hours_to_resolve)} to resolve`}
            />
            <Tile
              label="Documents ready"
              value={String(data.documents.ready)}
              note={`${count(data.documents.chunks, "passage")}${data.documents.failed ? ` · ${data.documents.failed} failed` : ""}`}
            />
            <Tile
              label="People"
              value={String(data.people.employee + data.people.manager + data.people.admin)}
              note={[count(data.people.employee, "employee"), count(data.people.manager, "manager"), count(data.people.admin, "admin")].join(" · ")}
            />
          </div>

          <div className="panel">
            <h2>Questions per day</h2>
            {q.total === 0 ? <p className="muted">No questions in this period yet.</p> : <QuestionsChart days={q.per_day} />}
          </div>

          <div className="panels">
            <div className="panel">
              <h2>What the documents don't cover</h2>
              <p className="muted small">The most-asked questions that got no answer. Each one is a document worth writing.</p>
              {q.top_gaps.length === 0 ? (
                <p className="muted">None in this period.</p>
              ) : (
                <table className="docs compact">
                  <thead>
                    <tr>
                      <th>Question</th>
                      <th className="num">Times</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.top_gaps.map((g) => (
                      <tr key={g.question}>
                        <td>{g.question}</td>
                        <td className="num">{g.times}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="panel">
              <h2>How questions ended</h2>
              <ShareRows rows={OUTCOME_ORDER.map((o) => ({ label: OUTCOME_LABEL[o], count: q.by_outcome[o] }))} />
              <h2 className="spaced">Tickets by status</h2>
              <ShareRows
                rows={[
                  { label: "Open", count: data.tickets.by_status.open },
                  { label: "In progress", count: data.tickets.by_status.in_progress },
                  { label: "Resolved", count: data.tickets.by_status.resolved },
                  { label: "Closed", count: data.tickets.by_status.closed },
                ]}
              />
            </div>
          </div>
        </>
      )}

      <div className="panel">
        <h2>Recent questions</h2>
        {questions.error && <div className="notice error">{questions.error}</div>}
        {questions.items?.length === 0 && <p className="muted">No questions yet.</p>}
        {questions.items && questions.items.length > 0 && (
          <div className="table-scroll">
            <table className="docs compact">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>Question</th>
                  <th>Outcome</th>
                  <th>Sources</th>
                  <th className="num">First word</th>
                </tr>
              </thead>
              <tbody>
                {questions.items.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{when.format(new Date(r.at))}</td>
                    <td>{r.user_name}</td>
                    <td>{r.question}</td>
                    <td>
                      <span className={`outcome ${r.outcome}`}>{OUTCOME_LABEL[r.outcome]}</span>
                    </td>
                    <td className="small-cell">{r.sources.join(", ") || "–"}</td>
                    <td className="num">{seconds(r.first_token_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {questions.more && (
          <button className="link" onClick={questions.loadMore}>
            Load more
          </button>
        )}
      </div>

      <div className="panel">
        <h2>Audit log</h2>
        {audit.error && <div className="notice error">{audit.error}</div>}
        {audit.items && (
          <ul className="audit">
            {audit.items.map((e) => (
              <li key={e.id}>
                <span className="muted small nowrap">{when.format(new Date(e.at))}</span>
                <strong>{e.actor ?? "Deleted user"}</strong>
                <span>{describeAudit(e)}</span>
              </li>
            ))}
          </ul>
        )}
        {audit.more && (
          <button className="link" onClick={audit.loadMore}>
            Load more
          </button>
        )}
      </div>
    </section>
  );
}

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError, changeTicketStatus, listTickets, type Ticket, type TicketStatus } from "../api";
import { isStaff, useAuth } from "../session";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

const STATUSES: TicketStatus[] = ["open", "in_progress", "resolved", "closed"];

const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

type Filter = TicketStatus | "all";

/** Managers and admins: change the status, with an optional note the employee sees. */
function StatusForm({ ticket, onSaved }: { ticket: Ticket; onSaved: (t: Ticket) => void }) {
  const [status, setStatus] = useState<TicketStatus>(ticket.status);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unchanged = status === ticket.status && !note.trim();

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onSaved(await changeTicketStatus(ticket.id, status, note.trim()));
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the ticket.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="status-form" onSubmit={save}>
      <label>
        Status
        <select value={status} onChange={(e) => setStatus(e.target.value as TicketStatus)} disabled={saving}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      <label className="grow">
        Note for {ticket.user_name} (optional)
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={1000}
          placeholder="e.g. Checked with HR: added to the benefits FAQ."
          disabled={saving}
        />
      </label>
      <button type="submit" disabled={saving || unchanged}>
        {saving ? "Saving…" : "Update"}
      </button>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
    </form>
  );
}

function History({ ticket }: { ticket: Ticket }) {
  if (ticket.history.length === 0) return null;
  return (
    <details className="history" open={ticket.history.some((e) => e.note)}>
      <summary>History ({ticket.history.length})</summary>
      <ol>
        {ticket.history.map((e, i) => (
          <li key={i}>
            <span className="muted small">
              {dateFormat.format(new Date(e.at))} · {e.user_name}
            </span>
            <div>
              {e.from_status === e.to_status ? (
                "Added a note"
              ) : (
                <>
                  {STATUS_LABEL[e.from_status]} → <strong>{STATUS_LABEL[e.to_status]}</strong>
                </>
              )}
            </div>
            {e.note && <blockquote>{e.note}</blockquote>}
          </li>
        ))}
      </ol>
    </details>
  );
}

export default function TicketsPage() {
  const { user } = useAuth();
  const everyone = isStaff(user);
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let cancelled = false;
    listTickets()
      .then((t) => {
        if (cancelled) return;
        setTickets(t);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load tickets.");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: 0, open: 0, in_progress: 0, resolved: 0, closed: 0 };
    for (const t of tickets ?? []) {
      c.all += 1;
      c[t.status] += 1;
    }
    return c;
  }, [tickets]);

  const shown = tickets?.filter((t) => filter === "all" || t.status === filter) ?? [];

  function replace(updated: Ticket) {
    setTickets((all) => all?.map((t) => (t.id === updated.id ? updated : t)) ?? null);
  }

  return (
    <section className="page">
      <h1>{everyone ? "All tickets" : "My tickets"}</h1>
      <p className="muted">
        {everyone
          ? "Questions the documents could not answer, from everyone. Move each one along and leave a note: the person who asked sees it."
          : "Questions you asked that the documents could not answer. The help desk's notes appear here."}
      </p>

      {error && (
        <div className="notice error" role="alert">
          {error} <button onClick={() => setAttempt((n) => n + 1)}>Retry</button>
        </div>
      )}
      {tickets === null && !error && <p className="muted">Loading tickets…</p>}
      {tickets?.length === 0 && (
        <p className="notice">No tickets yet. When the assistant can't answer a question, you can open one from the chat.</p>
      )}

      {tickets && tickets.length > 0 && (
        <>
          <div className="filters" role="tablist" aria-label="Filter by status">
            {(["all", ...STATUSES] as Filter[]).map((f) => (
              <button
                key={f}
                role="tab"
                aria-selected={filter === f}
                className={filter === f ? "on" : ""}
                onClick={() => setFilter(f)}
              >
                {f === "all" ? "All" : STATUS_LABEL[f]} <span className="count">{counts[f]}</span>
              </button>
            ))}
          </div>

          {shown.length === 0 && <p className="muted">No {STATUS_LABEL[filter as TicketStatus].toLowerCase()} tickets.</p>}

          <ul className="tickets">
            {shown.map((t) => (
              <li key={t.id}>
                <div className="ticket-head">
                  <strong>
                    #{t.id} {t.title}
                  </strong>
                  <span className={`status-pill ${t.status}`}>{STATUS_LABEL[t.status]}</span>
                </div>
                <div className="muted small">
                  {t.user_name} · opened {dateFormat.format(new Date(t.created_at))}
                </div>
                <p className="asked">“{t.question}”</p>
                {t.summary && <p>{t.summary}</p>}
                <History ticket={t} />
                {everyone && <StatusForm key={t.updated_at} ticket={t} onSaved={replace} />}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

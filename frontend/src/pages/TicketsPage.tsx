import { useEffect, useState } from "react";
import { ApiError, listTickets, type Ticket } from "../api";
import { isStaff, useAuth } from "../session";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export default function TicketsPage() {
  const { user } = useAuth();
  const everyone = isStaff(user);
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

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

  return (
    <section className="page">
      <h1>{everyone ? "All tickets" : "My tickets"}</h1>
      <p className="muted">
        {everyone
          ? "Questions the documents could not answer, from everyone, newest first."
          : "Questions you asked that the documents could not answer, newest first."}
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
        <ul className="tickets">
          {tickets.map((t) => (
            <li key={t.id}>
              <div className="ticket-head">
                <strong>
                  #{t.id} {t.title}
                </strong>
                <span className={`badge ${t.status}`}>{t.status}</span>
              </div>
              <div className="muted small">
                {t.user_name} · {dateFormat.format(new Date(t.created_at))}
              </div>
              <p className="asked">“{t.question}”</p>
              {t.summary && <p>{t.summary}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, createTicket, draftTicket, type Ticket, type TicketDraft } from "../api";

const NAME_KEY = "ask-onboarding:user-name";

function savedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return ""; // storage can be blocked, e.g. in private windows
  }
}

type Step =
  | { kind: "offer" }
  | { kind: "drafting" }
  | { kind: "review"; draft: TicketDraft }
  | { kind: "saving"; draft: TicketDraft }
  | { kind: "created"; ticket: Ticket }
  | { kind: "dismissed" };

/**
 * Shown under an answer the documents couldn't give.
 * offer -> the model drafts a ticket (tool call) -> the employee edits and confirms -> saved.
 */
export default function TicketOffer({ question }: { question: string }) {
  const [step, setStep] = useState<Step>({ kind: "offer" });
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [name, setName] = useState(savedName);
  const [error, setError] = useState<string | null>(null);

  async function startDraft() {
    setStep({ kind: "drafting" });
    setError(null);
    try {
      const draft = await draftTicket(question);
      setTitle(draft.title);
      setSummary(draft.summary);
      setStep({ kind: "review", draft });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not draft the ticket.");
      setStep({ kind: "offer" });
    }
  }

  async function save(e: FormEvent, draft: TicketDraft) {
    e.preventDefault();
    setStep({ kind: "saving", draft });
    setError(null);
    try {
      const ticket = await createTicket({ title, question, summary, user_name: name });
      try {
        localStorage.setItem(NAME_KEY, name.trim());
      } catch {
        // remembering the name is only a convenience
      }
      setStep({ kind: "created", ticket });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the ticket.");
      setStep({ kind: "review", draft });
    }
  }

  if (step.kind === "dismissed") return null;

  if (step.kind === "created")
    return (
      <div className="ticket done">
        Ticket #{step.ticket.id} created. The help desk will follow up. <Link to="/tickets">View tickets</Link>
      </div>
    );

  if (step.kind === "offer" || step.kind === "drafting")
    return (
      <div className="ticket">
        <span>Want the help desk to answer this?</span>
        <div className="actions">
          <button onClick={startDraft} disabled={step.kind === "drafting"}>
            {step.kind === "drafting" ? "Drafting a ticket…" : "Yes, open a ticket"}
          </button>
          <button className="secondary" onClick={() => setStep({ kind: "dismissed" })} disabled={step.kind === "drafting"}>
            No thanks
          </button>
        </div>
        {error && <div className="notice error" role="alert">{error}</div>}
      </div>
    );

  const saving = step.kind === "saving";
  return (
    <form className="ticket" onSubmit={(e) => save(e, step.draft)}>
      <strong>Review your ticket</strong>
      <span className="muted small">
        {step.draft.drafted_by === "model"
          ? "Drafted by the assistant. Edit anything before you send it."
          : "The assistant couldn't draft this, so we started from your question."}
      </span>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required disabled={saving} />
      </label>
      <label>
        Details for the help desk
        <textarea value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={1000} rows={3} disabled={saving} />
      </label>
      <label>
        Your name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required disabled={saving} />
      </label>
      <div className="actions">
        <button type="submit" disabled={saving || !title.trim() || !name.trim()}>
          {saving ? "Creating…" : "Create ticket"}
        </button>
        <button type="button" className="secondary" onClick={() => setStep({ kind: "dismissed" })} disabled={saving}>
          Cancel
        </button>
      </div>
      {error && <div className="notice error" role="alert">{error}</div>}
    </form>
  );
}

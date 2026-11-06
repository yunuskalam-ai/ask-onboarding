import { useEffect, useRef, useState, type FormEvent } from "react";
import { NO_ANSWER, streamChat, type Citation, type DoneReason, type Turn } from "../api";
import AnswerText from "../components/AnswerText";
import SourcePanel from "../components/SourcePanel";

type Message =
  | { id: number; role: "user"; text: string }
  | {
      id: number;
      role: "assistant";
      text: string;
      state: "streaming" | "done" | "error";
      reason?: DoneReason;
      citations: Citation[];
      error?: string;
    };

const EXAMPLES = [
  "How many days of annual leave do I get?",
  "Can I deploy to production on a Friday?",
  "How do I reset my password?",
];

let nextId = 1;

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<Citation | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abort.current?.abort(), []); // stop streaming when leaving the page

  function updateAssistant(id: number, change: (m: Extract<Message, { role: "assistant" }>) => Partial<Message>) {
    setMessages((all) => all.map((m) => (m.id === id && m.role === "assistant" ? ({ ...m, ...change(m) } as Message) : m)));
  }

  async function ask(question: string) {
    question = question.trim();
    if (!question || busy) return;

    // Earlier finished turns, so follow-up questions have context.
    const history: Turn[] = messages
      .filter((m) => m.role === "user" || m.state === "done")
      .map((m) => ({ role: m.role, content: m.text }));

    const answerId = nextId + 1;
    setMessages((all) => [
      ...all,
      { id: nextId, role: "user", text: question },
      { id: answerId, role: "assistant", text: "", state: "streaming", citations: [] },
    ]);
    nextId += 2;
    setInput("");
    setBusy(true);
    abort.current = new AbortController();

    await streamChat(
      question,
      history,
      {
        onToken: (text) => updateAssistant(answerId, (m) => ({ text: m.text + text })),
        onDone: (done) =>
          updateAssistant(answerId, (m) => ({
            state: "done",
            reason: done.reason,
            citations: done.citations,
            // A safety refusal may have streamed partial text: replace it.
            text: done.reason === "refused" ? NO_ANSWER : m.text.trim(),
          })),
        onError: (message) => updateAssistant(answerId, () => ({ state: "error", error: message })),
      },
      abort.current.signal,
    );
    setBusy(false);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    ask(input);
  }

  return (
    <div className={`chat-layout ${source ? "with-source" : ""}`}>
      <section className="chat">
        <div className="messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="empty">
              <h1>Ask anything about working here</h1>
              <p className="muted">Answers come only from company documents, with a link to the exact passage.</p>
              <div className="examples">
                {EXAMPLES.map((q) => (
                  <button key={q} onClick={() => ask(q)} disabled={busy}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="msg user">
                {m.text}
              </div>
            ) : (
              <div key={m.id} className={`msg assistant ${m.reason && m.reason !== "answered" ? "no-answer" : ""}`}>
                {m.state === "streaming" && !m.text && <span className="muted">Searching the documents…</span>}
                <AnswerText text={m.text} citations={m.citations} onCite={setSource} />
                {m.state === "streaming" && m.text && <span className="cursor" aria-hidden />}
                {m.state === "error" && (
                  <div className="notice error" role="alert">
                    {m.error}
                  </div>
                )}
                {m.state === "done" && m.reason === "answered" && m.citations.length === 0 && (
                  <div className="muted small">This answer did not cite a source, so check it before relying on it.</div>
                )}
                {m.state === "done" && m.citations.length > 0 && (
                  <div className="sources">
                    Sources:{" "}
                    {m.citations.map((c) => (
                      <button key={c.n} className="link" onClick={() => setSource(c)}>
                        [{c.n}] {c.filename}
                        {c.page ? ` p.${c.page}` : ""}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ),
          )}
          <div ref={bottom} />
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about policies, IT, engineering…"
            maxLength={1000}
            disabled={busy}
            aria-label="Your question"
          />
          <button type="submit" disabled={busy || !input.trim()}>
            {busy ? "Answering…" : "Ask"}
          </button>
        </form>
      </section>

      {source && <SourcePanel key={source.document_id} citation={source} onClose={() => setSource(null)} />}
    </div>
  );
}

import { useEffect, useState } from "react";

// What the assistant is doing before the first word arrives. On a CPU the first
// word can take 10-20 seconds, so the text moves on rather than sitting still.
const STEPS = [
  { after: 0, text: "Searching the documents" },
  { after: 2500, text: "Reading the sources" },
  { after: 10000, text: "Still working. Answers take a little longer on this server" },
];

/** Animated dots plus a status line, shown until the answer starts streaming. */
export default function TypingIndicator() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timers = STEPS.slice(1).map((s, i) => setTimeout(() => setStep(i + 1), s.after));
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <span className="typing" role="status" aria-live="polite">
      <span className="typing-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="muted">{STEPS[step].text}…</span>
    </span>
  );
}

import { Link } from "react-router-dom";
import { useAuth } from "../session";

// The numbers come from eval/run_eval.py (see the README's Evaluation section).
const RESULTS = [
  { value: "94%", label: "of answerable questions answered correctly" },
  { value: "4 of 4", label: "out-of-scope questions honestly refused" },
  { value: "0", label: "false “I don't know” answers" },
  { value: "No API key", label: "the model runs on the server; documents never leave it" },
];

const STEPS = [
  { title: "Ask", text: "Type a question the way you'd ask a colleague on your first week." },
  {
    title: "Find",
    text: "Hybrid search (meaning plus keywords) picks the five passages from the handbook and wiki most likely to answer it.",
  },
  {
    title: "Cite",
    text: "The answer names its sources. Click a number to open the document with the exact passage highlighted.",
  },
];

const ROLES = [
  { role: "employee", name: "Employee", can: ["Ask questions with cited answers", "Open tickets for anything the documents miss", "Follow their own tickets"] },
  { role: "manager", name: "Manager", can: ["Everything an employee can do", "See their team's tickets and reply", "Browse the document library"] },
  { role: "admin", name: "Admin", can: ["Every ticket, from everyone", "Upload, replace and delete company documents", "Add people, set roles, managers and departments", "See the overview and system alerts"] },
];

function Preview() {
  return (
    <div className="preview" aria-label="Example of a cited answer">
      <div className="preview-msg user">Can I deploy to production on a Friday?</div>
      <div className="preview-msg assistant">
        No. Production deploys are allowed Monday to Thursday, 10:00 to 16:00 UK time, and never on Fridays
        <span className="preview-cite">1</span>.
      </div>
      <div className="preview-source">
        <div className="preview-file">
          <span className="preview-cite">1</span> eng-deployment-and-releases.md
        </div>
        <p>
          Production deploys are allowed Monday to Thursday, 10:00 to 16:00 UK time.{" "}
          <mark>No deploys on Fridays, weekends or UK bank holidays.</mark>
        </p>
      </div>
    </div>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const start = user ? (
    <Link to="/chat" className="button">
      Open the assistant
    </Link>
  ) : (
    <Link to="/sign-in" className="button">
      Sign in to try it
    </Link>
  );

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-text">
          <p className="eyebrow">Onboarding assistant · Larkspur Labs</p>
          <h1>Answers from your company's own documents, with the source one click away.</h1>
          <p className="lead">
            New starters ask in plain English. Ask Onboarding finds the passage that answers it and shows exactly
            where it came from. When the documents don't say, it tells you so and drafts a help-desk ticket.
          </p>
          <div className="hero-actions">
            {start}
            <a href="#how" className="button ghost">
              How it works
            </a>
          </div>
        </div>
        <Preview />
      </section>

      <section className="band" id="how">
        <h2>How it works</h2>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="step-number">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="band">
        <h2>Honest by design</h2>
        <p className="band-lead">
          A guess that sounds confident is worse than “I don't know”. Measured on 20 held-out questions:
        </p>
        <ul className="results">
          {RESULTS.map((r) => (
            <li key={r.label}>
              <strong>{r.value}</strong>
              <span>{r.label}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="band">
        <h2>Who can do what</h2>
        <div className="role-cards">
          {ROLES.map((r) => (
            <div key={r.role} className={`role-card role-${r.role}`}>
              <h3>{r.name}</h3>
              <ul>
                {r.can.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="hero-actions centered">{start}</div>
      </section>

      <footer className="home-footer muted small">
        Larkspur Labs is a fictional company. Source code:{" "}
        <a href="https://github.com/yunuskalam-ai/ask-onboarding">github.com/yunuskalam-ai/ask-onboarding</a>
      </footer>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, listAccounts, type User } from "../api";
import { ROLE_LABEL, initials, useAuth } from "../session";

/** Only follow links inside this app after signing in, never to another site. */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/chat";
}

export default function SignInPage() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [accounts, setAccounts] = useState<User[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // email being signed in
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAccounts()
      .then(setAccounts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the accounts."));
  }, []);

  if (user) return <Navigate to={next} replace />;

  async function choose(account: User) {
    setBusy(account.email);
    setError(null);
    try {
      await signIn(account.email);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
      setBusy(null);
    }
  }

  return (
    <section className="sign-in">
      <div className="sign-in-card">
        <h1>Sign in</h1>
        <p className="muted">
          Choose who you want to be. This demo has no passwords; a real deployment would use the company's single
          sign-on here, and everything after this step stays the same.
        </p>

        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {accounts === null && !error && <p className="muted">Loading accounts…</p>}

        <ul className="accounts">
          {accounts?.map((a) => (
            <li key={a.id}>
              <button onClick={() => choose(a)} disabled={busy !== null}>
                <span className={`avatar role-${a.role}`}>{initials(a.name)}</span>
                <span className="account-who">
                  <strong>{a.name}</strong>
                  <span className="muted small">{a.email}</span>
                </span>
                <span className={`role-pill role-${a.role}`}>{ROLE_LABEL[a.role]}</span>
                <span className="account-go" aria-hidden="true">
                  {busy === a.email ? "…" : "→"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

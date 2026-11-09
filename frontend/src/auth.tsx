// Who is signed in, for the whole app. The server is the real gatekeeper:
// it checks the role on every request. The UI only hides what you can't use.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import * as api from "./api";
import type { Role, User } from "./api";
import { AuthContext, ROLE_LABEL, useAuth } from "./session";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api.setSignedOutHandler(() => setUser(null)); // any 401 = the session is gone
    api
      .getMe()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  const signIn = useCallback(async (email: string) => {
    const signedIn = await api.signIn(email);
    setUser(signedIn);
    return signedIn;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.signOut();
    } finally {
      setUser(null); // leave the app even if the server was unreachable
    }
  }, []);

  const refresh = useCallback(async () => {
    setUser(await api.getMe().catch(() => null));
  }, []);

  const value = useMemo(() => ({ user, signIn, signOut, refresh }), [user, signIn, signOut, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Only render the page for signed-in users with one of these roles. */
export function RequireRole({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <p className="page muted">Loading…</p>;
  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/sign-in?next=${next}`} replace />;
  }
  if (roles && !roles.includes(user.role))
    return (
      <section className="page">
        <h1>Not available for your role</h1>
        <p className="muted">
          This page needs the {roles.map((r) => ROLE_LABEL[r]).join(" or ")} role. You're signed in as{" "}
          {ROLE_LABEL[user.role].toLowerCase()}.
        </p>
      </section>
    );
  return <>{children}</>;
}

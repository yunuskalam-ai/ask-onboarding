import { useEffect, useState } from "react";
import { ApiError, changeRole, listUsers, type Role, type User } from "../api";
import { ROLE_LABEL, initials, useAuth } from "../session";

const ROLES: Role[] = ["employee", "manager", "admin"];

/** Admins only: who has which role. The server refuses to remove the last admin. */
export default function PeoplePage() {
  const { user: me, refresh } = useAuth();
  const [people, setPeople] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<number | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    listUsers()
      .then(setPeople)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load people."));
  }, []);

  async function onChange(person: User, role: Role) {
    setSaving(person.id);
    setError(null);
    setSaved(null);
    try {
      const updated = await changeRole(person.id, role);
      setPeople((all) => all?.map((p) => (p.id === updated.id ? updated : p)) ?? null);
      setSaved(`${updated.name} is now ${ROLE_LABEL[updated.role].toLowerCase()}.`);
      if (updated.id === me?.id) await refresh(); // your own role changed: menus and pages follow
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the role.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <section className="page">
      <h1>People</h1>
      <p className="muted">
        Change what each person can do. Changes apply straight away, even to someone who is signed in. There must
        always be at least one admin.
      </p>

      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {saved && (
        <div className="notice success" role="status">
          {saved}
        </div>
      )}
      {people === null && !error && <p className="muted">Loading people…</p>}

      {people && (
        <table className="docs people">
          <thead>
            <tr>
              <th>Person</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {people.map((p) => (
              <tr key={p.id}>
                <td>
                  <div className="person">
                    <span className={`avatar role-${p.role}`}>{initials(p.name)}</span>
                    <span className="account-who">
                      <strong>
                        {p.name} {p.id === me?.id && <span className="muted small">(you)</span>}
                      </strong>
                      <span className="muted small">{p.email}</span>
                    </span>
                  </div>
                </td>
                <td>
                  <select
                    aria-label={`Role for ${p.name}`}
                    value={p.role}
                    disabled={saving !== null}
                    onChange={(e) => onChange(p, e.target.value as Role)}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

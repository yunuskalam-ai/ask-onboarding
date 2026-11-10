import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  addDepartment,
  addPerson,
  changePerson,
  deleteDepartment,
  listDepartments,
  listPeople,
  renameDepartment,
  type Department,
  type Person,
  type Role,
} from "../api";
import { changesFrom, draftOf, type Draft } from "../personEdit";
import { ROLE_LABEL, initials, useAuth } from "../session";
import { buildTree, type TreeNode } from "../teamTree";

const ROLES: Role[] = ["employee", "manager", "admin"];

const message = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

type SelectProps = {
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  label: string;
};

/** Choose a manager: active managers and admins, never the person themselves. */
function ManagerSelect({ value, onChange, disabled, label, people, exclude }: SelectProps & { people: Person[]; exclude?: number }) {
  const managers = people.filter((p) => p.active && p.role !== "employee" && p.id !== exclude);
  return (
    <select aria-label={label} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">No manager</option>
      {managers.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name}
        </option>
      ))}
    </select>
  );
}

function DepartmentSelect({ value, onChange, disabled, label, departments }: SelectProps & { departments: Department[] }) {
  return (
    <select aria-label={label} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">No department</option>
      {departments.map((d) => (
        <option key={d.id} value={d.id}>
          {d.name}
        </option>
      ))}
    </select>
  );
}

function AddPersonForm({ people, departments, onAdded }: { people: Person[]; departments: Department[]; onAdded: (p: Person) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("employee");
  const [department, setDepartment] = useState<number | null>(null);
  const [manager, setManager] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onAdded(await addPerson({ name, email, role, department_id: department, manager_id: manager }));
      setName("");
      setEmail("");
      setManager(null);
    } catch (err) {
      setError(message(err, "Could not add the person."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel person-form" onSubmit={submit}>
      <h2>Add a person</h2>
      <div className="form-grid">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} disabled={saving} />
        </label>
        <label>
          Work email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={200} disabled={saving} />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} disabled={saving}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Department
          <DepartmentSelect label="Department" value={department} departments={departments} onChange={setDepartment} disabled={saving} />
        </label>
        <label>
          Reports to
          <ManagerSelect label="Reports to" value={manager} people={people} onChange={setManager} disabled={saving} />
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={saving || !name.trim() || !email.trim()}>
          {saving ? "Adding…" : "Add person"}
        </button>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
    </form>
  );
}

/** One person's role, department, manager and status, saved together or not at all. */
function EditPerson({
  person,
  people,
  departments,
  self,
  onSaved,
  onCancel,
}: {
  person: Person;
  people: Person[];
  departments: Department[];
  self: boolean;
  onSaved: (done: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(person));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const change = changesFrom(person, draft);
  const deactivating = change.active === false;
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await changePerson(person.id, change);
      onSaved(
        deactivating
          ? `${person.name} is now inactive and has been signed out.`
          : change.active
            ? `${person.name} is active again.`
            : `${person.name}'s changes were saved.`,
      );
    } catch (err) {
      setError(message(err, "Could not save the change."));
      setSaving(false);
    }
  }

  return (
    <form className="person-form edit-person" onSubmit={save} aria-label={`Edit ${person.name}`}>
      <div className="form-grid">
        <label>
          Role
          <select value={draft.role} onChange={(e) => set({ role: e.target.value as Role })} disabled={saving}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Department
          <DepartmentSelect label="Department" value={draft.department_id} departments={departments} onChange={(id) => set({ department_id: id })} disabled={saving} />
        </label>
        <label>
          Reports to
          <ManagerSelect label="Reports to" value={draft.manager_id} people={people} exclude={person.id} onChange={(id) => set({ manager_id: id })} disabled={saving} />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.active}
            onChange={(e) => set({ active: e.target.checked })}
            disabled={saving || self}
            title={self ? "You can't deactivate yourself" : undefined}
          />
          Active (can sign in)
        </label>
      </div>
      {deactivating && (
        <div className="notice warning" role="alert">
          {person.name} will be signed out everywhere straight away and can't sign in until made active again. Their tickets stay.
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="actions">
        <button type="submit" className={deactivating ? "danger" : ""} disabled={saving || Object.keys(change).length === 0}>
          {saving ? "Saving…" : deactivating ? "Deactivate and save" : "Save changes"}
        </button>
        <button type="button" className="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function DepartmentsPanel({ departments, onChanged }: { departments: Department[]; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setError(null);
    try {
      await action();
      onChanged();
      return true;
    } catch (err) {
      setError(message(err, "That didn't work."));
      return false;
    }
  }

  async function rename(e: FormEvent, id: number, newName: string) {
    e.preventDefault();
    if (await run(() => renameDepartment(id, newName))) setEditing(null);
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (await run(() => addDepartment(name))) setName("");
  }

  return (
    <div className="panel">
      <h2>Departments</h2>
      <ul className="departments">
        {departments.map((d) => (
          <li key={d.id}>
            {editing?.id === d.id ? (
              <form className="inline-form" onSubmit={(e) => rename(e, d.id, editing.name)}>
                <input aria-label="New name" value={editing.name} onChange={(e) => setEditing({ id: d.id, name: e.target.value })} maxLength={60} />
                <button type="submit">Save</button>
                <button type="button" className="secondary" onClick={() => setEditing(null)}>
                  Cancel
                </button>
              </form>
            ) : (
              <>
                <span>
                  <strong>{d.name}</strong>{" "}
                  <span className="muted small">
                    {d.people} {d.people === 1 ? "person" : "people"}
                  </span>
                </span>
                <span className="row-actions">
                  <button className="link" onClick={() => setEditing({ id: d.id, name: d.name })}>
                    Rename
                  </button>
                  <button
                    className="link danger"
                    disabled={d.people > 0}
                    title={d.people > 0 ? "Move its people to another department first" : undefined}
                    onClick={() => run(() => deleteDepartment(d.id))}
                  >
                    Delete
                  </button>
                </span>
              </>
            )}
          </li>
        ))}
        {departments.length === 0 && <li className="muted">No departments yet.</li>}
      </ul>
      <form className="inline-form" onSubmit={add}>
        <input aria-label="Department name" placeholder="New department" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        <button type="submit" disabled={!name.trim()}>
          Add
        </button>
      </form>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

function Tree({ nodes }: { nodes: TreeNode<Person>[] }) {
  return (
    <ul className="tree">
      {nodes.map(({ person, reports }) => (
        <li key={person.id}>
          <span className={person.active ? "" : "muted"}>
            {person.name} <span className={`role-pill role-${person.role}`}>{ROLE_LABEL[person.role]}</span>
            {person.department && <span className="muted small"> · {person.department.name}</span>}
            {!person.active && <span className="muted small"> · inactive</span>}
          </span>
          {reports.length > 0 && <Tree nodes={reports} />}
        </li>
      ))}
    </ul>
  );
}

/** Admins only: people, their roles, departments and reporting lines. */
export default function PeoplePage() {
  const { user: me, refresh } = useAuth();
  const [people, setPeople] = useState<Person[] | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState<number | "all">("all");
  const [showInactive, setShowInactive] = useState(false);

  const reload = useCallback(() => {
    Promise.all([listPeople(), listDepartments()])
      .then(([p, d]) => {
        setPeople(p);
        setDepartments(d);
      })
      .catch((err) => setError(message(err, "Could not load people.")));
  }, []);

  useEffect(reload, [reload]);

  function startEditing(id: number) {
    setEditing(id);
    setSaved(null);
  }

  async function onSaved(person: Person, done: string) {
    setEditing(null);
    setSaved(done);
    reload(); // reports counts, departments and the tree all follow
    if (person.id === me?.id) await refresh(); // your own role changed: menus and pages follow
  }

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (people ?? []).filter(
      (p) =>
        (showInactive || p.active) &&
        (departmentFilter === "all" || p.department?.id === departmentFilter) &&
        (!q || p.name.toLowerCase().includes(q) || p.email.includes(q)),
    );
  }, [people, search, departmentFilter, showInactive]);

  const tree = useMemo(() => buildTree(people ?? []), [people]);
  const inactiveCount = people?.filter((p) => !p.active).length ?? 0;

  return (
    <section className="page wide">
      <h1>People</h1>
      <p className="muted">
        Add people, set their role, department and manager, and deactivate anyone who has left. A manager sees and
        handles the tickets of everyone below them; admins see everything. Choose Edit to change someone.
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
        <>
          <div className="panel">
            <div className="toolbar">
              <input type="search" aria-label="Search people" placeholder="Search by name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
              <select
                aria-label="Filter by department"
                value={departmentFilter}
                onChange={(e) => setDepartmentFilter(e.target.value === "all" ? "all" : Number(e.target.value))}
              >
                <option value="all">All departments</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
              <label className="checkbox">
                <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
                Show inactive ({inactiveCount})
              </label>
            </div>
            <div className="table-scroll">
              <table className="docs people">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Role</th>
                    <th>Department</th>
                    <th>Reports to</th>
                    <th className="num">Reports</th>
                    <th>Status</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((p) => (
                    <Fragment key={p.id}>
                      <tr className={[p.active ? "" : "inactive", editing === p.id ? "editing" : ""].join(" ").trim()}>
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
                          <span className={`role-pill role-${p.role}`}>{ROLE_LABEL[p.role]}</span>
                        </td>
                        <td>{p.department?.name ?? <span className="muted">None</span>}</td>
                        <td>{p.manager?.name ?? <span className="muted">Nobody</span>}</td>
                        <td className="num">{p.reports}</td>
                        <td>
                          <span className={`state-pill ${p.active ? "on" : ""}`}>{p.active ? "Active" : "Inactive"}</span>
                        </td>
                        <td className="num">
                          {editing !== p.id && (
                            <button className="link" onClick={() => startEditing(p.id)} aria-label={`Edit ${p.name}`}>
                              Edit
                            </button>
                          )}
                        </td>
                      </tr>
                      {editing === p.id && (
                        <tr className="edit-row">
                          <td colSpan={7}>
                            <EditPerson
                              person={p}
                              people={people}
                              departments={departments}
                              self={p.id === me?.id}
                              onSaved={(done) => onSaved(p, done)}
                              onCancel={() => setEditing(null)}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                  {shown.length === 0 && (
                    <tr>
                      <td colSpan={7} className="muted">
                        Nobody matches.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panels">
            <AddPersonForm
              people={people}
              departments={departments}
              onAdded={(p) => {
                setSaved(`${p.name} was added.`);
                reload();
              }}
            />
            <DepartmentsPanel departments={departments} onChanged={reload} />
          </div>

          <div className="panel">
            <h2>Team structure</h2>
            <p className="muted small">Who reports to whom. A manager's team is everyone below them.</p>
            <Tree nodes={tree} />
          </div>
        </>
      )}
    </section>
  );
}

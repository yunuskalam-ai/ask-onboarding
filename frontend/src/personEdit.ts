import type { Person, PersonChange, Role } from "./api";

/** What the People page's edit form holds for one person. */
export type Draft = { role: Role; department_id: number | null; manager_id: number | null; active: boolean };

export const draftOf = (p: Person): Draft => ({
  role: p.role,
  department_id: p.department?.id ?? null,
  manager_id: p.manager?.id ?? null,
  active: p.active,
});

/** Only the fields the admin actually changed, so Save sends one small, honest PATCH. */
export function changesFrom(p: Person, draft: Draft): PersonChange {
  const before = draftOf(p);
  const change: PersonChange = {};
  if (draft.role !== before.role) change.role = draft.role;
  if (draft.department_id !== before.department_id) change.department_id = draft.department_id;
  if (draft.manager_id !== before.manager_id) change.manager_id = draft.manager_id;
  if (draft.active !== before.active) change.active = draft.active;
  return change;
}

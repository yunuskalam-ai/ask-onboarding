// Reporting lines as a tree, for the People page. Pure, so it can be tested.

export type TreeInput = { id: number; name: string; manager: { id: number } | null };

export type TreeNode<T extends TreeInput> = { person: T; reports: TreeNode<T>[] };

/**
 * Top-level people are those with no manager, or whose manager isn't in the
 * list. Each person appears exactly once, even if the data contained a loop
 * (the server refuses loops; this is a second line of defence for the page).
 */
export function buildTree<T extends TreeInput>(people: T[]): TreeNode<T>[] {
  const byId = new Map(people.map((p) => [p.id, p]));
  const reportsOf = new Map<number, T[]>();
  for (const p of people) {
    if (p.manager && byId.has(p.manager.id)) {
      reportsOf.set(p.manager.id, [...(reportsOf.get(p.manager.id) ?? []), p]);
    }
  }
  const placed = new Set<number>();
  const byName = (a: T, b: T) => a.name.localeCompare(b.name);
  const grow = (person: T): TreeNode<T> => {
    placed.add(person.id);
    const reports = (reportsOf.get(person.id) ?? []).filter((r) => !placed.has(r.id)).sort(byName);
    return { person, reports: reports.map(grow) };
  };
  const roots = people.filter((p) => !p.manager || !byId.has(p.manager.id)).sort(byName).map(grow);
  // Anyone still unplaced is in a loop with no way in from the top: show them at the top level.
  for (const p of [...people].sort(byName)) if (!placed.has(p.id)) roots.push(grow(p));
  return roots;
}

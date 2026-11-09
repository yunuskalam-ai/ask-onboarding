import { describe, expect, it } from "vitest";
import { buildTree, type TreeInput, type TreeNode } from "./teamTree";

const person = (id: number, name: string, manager: number | null = null): TreeInput => ({
  id,
  name,
  manager: manager === null ? null : { id: manager },
});

/** "Alex(Jordan(Priya,Sam))" */
const show = (nodes: TreeNode<TreeInput>[]): string =>
  nodes.map((n) => n.person.name + (n.reports.length ? `(${show(n.reports)})` : "")).join(",");

describe("buildTree", () => {
  it("nests people under their managers, sorted by name", () => {
    const people = [person(3, "Sam", 2), person(1, "Alex"), person(4, "Priya", 2), person(2, "Jordan", 1)];
    expect(show(buildTree(people))).toBe("Alex(Jordan(Priya,Sam))");
  });

  it("people with no manager, or a manager not in the list, are at the top", () => {
    expect(show(buildTree([person(1, "Bea"), person(2, "Ann", 99)]))).toBe("Ann,Bea");
  });

  it("a loop in the data can't hang the page or drop anyone", () => {
    const loop = [person(1, "A", 2), person(2, "B", 1), person(3, "C")];
    const tree = buildTree(loop);
    const names: string[] = [];
    const walk = (nodes: TreeNode<TreeInput>[]) => nodes.forEach((n) => (names.push(n.person.name), walk(n.reports)));
    walk(tree);
    expect(names.sort()).toEqual(["A", "B", "C"]); // each exactly once
  });

  it("an empty list is an empty tree", () => {
    expect(buildTree([])).toEqual([]);
  });
});

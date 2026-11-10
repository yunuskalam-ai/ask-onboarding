import { describe, expect, it } from "vitest";
import type { Person } from "./api";
import { changesFrom, draftOf } from "./personEdit";

const person: Person = {
  id: 7,
  name: "Sam Lee",
  email: "sam@yklabs.example",
  role: "employee",
  active: true,
  department: { id: 2, name: "Sales" },
  manager: { id: 3, name: "Priya" },
  reports: 0,
} as Person;

describe("changesFrom", () => {
  it("is empty when nothing changed, so Save stays disabled", () => {
    expect(changesFrom(person, draftOf(person))).toEqual({});
  });

  it("sends only the changed fields", () => {
    expect(changesFrom(person, { ...draftOf(person), role: "manager", manager_id: null })).toEqual({ role: "manager", manager_id: null });
  });

  it("clearing a department sends null, not a missing field", () => {
    expect(changesFrom(person, { ...draftOf(person), department_id: null })).toEqual({ department_id: null });
  });

  it("deactivation is a change of its own", () => {
    expect(changesFrom(person, { ...draftOf(person), active: false })).toEqual({ active: false });
  });
});

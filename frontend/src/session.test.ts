import { describe, expect, it } from "vitest";
import type { User } from "./api";
import { initials, isAdmin, isStaff } from "./session";

const user = (role: User["role"]): User => ({ id: 1, email: "a@b.c", name: "A B", role });

describe("role helpers", () => {
  it("staff means manager or admin", () => {
    expect([isStaff(user("employee")), isStaff(user("manager")), isStaff(user("admin"))]).toEqual([false, true, true]);
  });

  it("only admins are admins", () => {
    expect([isAdmin(user("employee")), isAdmin(user("manager")), isAdmin(user("admin"))]).toEqual([false, false, true]);
  });

  it("signed out or still loading has no rights", () => {
    expect([isStaff(null), isStaff(undefined), isAdmin(null), isAdmin(undefined)]).toEqual([false, false, false, false]);
  });
});

describe("initials", () => {
  it.each([
    ["Sam Rivera", "SR"],
    ["alex morgan", "AM"],
    ["Priya", "P"],
    ["Mary Ann Lee", "MA"],
    ["  Sam   Rivera ", "SR"],
  ])("%s -> %s", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});

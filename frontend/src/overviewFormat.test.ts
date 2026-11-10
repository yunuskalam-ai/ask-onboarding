import { describe, expect, it } from "vitest";
import type { AuditEntry } from "./api";
import { count, describeAudit, describeClient, hours, localDate, percent, seconds } from "./overviewFormat";

const entry = (action: string, details: Record<string, unknown> = {}): AuditEntry => ({
  id: 1,
  at: "2026-11-10T10:00:00Z",
  actor: "Alex",
  action,
  details,
  ip: null,
  location: null,
  browser: null,
  os: null,
  device: null,
});

describe("describeClient", () => {
  it.each([
    ["Chrome 131", "Windows", "Chrome 131 on Windows"],
    ["curl 8", null, "curl 8"],
    [null, "Android 15", "Android 15"],
    [null, null, "–"],
  ])("%s / %s", (browser, os, expected) => expect(describeClient({ browser, os })).toBe(expected));
});

describe("formatting", () => {
  it("shows missing numbers as a dash, not 0 or NaN", () => {
    expect([seconds(null), percent(null), hours(null)]).toEqual(["–", "–", "–"]);
  });

  // \u00a0 is a no-break space: the unit never wraps onto its own line.
  it.each([
    [1234, "1.2\u00a0s"],
    [640, "0.6\u00a0s"],
    [0, "0.0\u00a0s"],
  ])("seconds(%d) = %s", (ms, expected) => expect(seconds(ms)).toBe(expected));

  it.each([
    [0.6, "60%"],
    [1, "100%"],
    [0, "0%"],
    [0.6667, "67%"],
  ])("percent(%d) = %s", (rate, expected) => expect(percent(rate)).toBe(expected));

  it.each([
    [3.25, "3.3\u00a0h"],
    [0.5, "30\u00a0min"],
    [0.001, "1\u00a0min"], // never "0 min"
  ])("hours(%d) = %s", (h, expected) => expect(hours(h)).toBe(expected));
});

describe("count", () => {
  it.each([
    [0, "managers"],
    [1, "manager"],
    [2, "managers"],
  ])("%d -> %s", (n, noun) => expect(count(n, "manager")).toBe(`${n}\u00a0${noun}`));
});

describe("localDate", () => {
  it("keeps the calendar day in every time zone", () => {
    const d = localDate("2026-11-09");
    expect([d.getFullYear(), d.getMonth(), d.getDate(), d.getHours()]).toEqual([2026, 10, 9, 0]);
  });
});

describe("describeAudit", () => {
  it.each([
    [entry("sign_in"), "Signed in"],
    [entry("document.upload", { filename: "faq.txt", unchanged: false }), "Uploaded faq.txt"],
    [entry("document.upload", { filename: "faq.txt", unchanged: true }), "Re-uploaded faq.txt (unchanged)"],
    [entry("user.role", { user: "sam@x", old: "employee", new: "manager" }), "Changed sam@x from employee to manager"],
    [entry("ticket.create", { ticket: 4, title: "Gym" }), "Opened ticket #4: Gym"],
    [entry("ticket.status", { ticket: 4, old: "open", new: "in_progress" }), "Moved ticket #4 from Open to In progress"],
  ])("%#: %s", (e, expected) => expect(describeAudit(e)).toBe(expected));

  it("an unknown action still shows its name", () => {
    expect(describeAudit(entry("export.started"))).toBe("export.started");
  });

  it("missing or odd details never crash", () => {
    expect(describeAudit(entry("user.role", { user: { nested: true } }))).toBe("Changed ? from ? to ?");
  });
});

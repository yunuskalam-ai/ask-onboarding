import { describe, expect, it } from "vitest";
import { timeAgo } from "./timeAgo";

const NOW = new Date("2026-11-10T12:00:00Z");
const ago = (seconds: number) => new Date(NOW.getTime() - seconds * 1000).toISOString();

describe("timeAgo", () => {
  it.each([
    [5, "just now"],
    [59, "just now"],
    [60, "1 min ago"],
    [59 * 60, "59 min ago"],
    [3600, "1 h ago"],
    [23 * 3600, "23 h ago"],
    [86400, "yesterday"],
    [3 * 86400, "3 days ago"],
  ])("%d seconds ago -> %s", (seconds, expected) => {
    expect(timeAgo(ago(seconds), NOW)).toBe(expected);
  });

  it("a clock slightly ahead of the server never shows a negative time", () => {
    expect(timeAgo(new Date(NOW.getTime() + 5000).toISOString(), NOW)).toBe("just now");
  });

  it("older than a week shows the date", () => {
    expect(timeAgo(ago(30 * 86400), NOW)).not.toMatch(/ago/);
  });
});

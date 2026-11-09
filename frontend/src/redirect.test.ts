import { describe, expect, it } from "vitest";
import { safeNext } from "./redirect";

describe("safeNext", () => {
  it.each([
    ["/tickets", "/tickets"],
    ["/chat?x=1#top", "/chat?x=1#top"],
    ["/people", "/people"],
    ["/a/../tickets", "/tickets"], // normalised like the browser would
  ])("follows in-app path %s", (next, expected) => {
    expect(safeNext(next)).toBe(expected);
  });

  it.each([
    [null],
    [""],
    ["https://evil.example"], // another site
    ["//evil.example"], // protocol-relative: the browser treats it as another host
    ["/\\evil.example"], // backslash: some browsers read /\ as //
    ["\\\\evil.example"],
    ["javascript:alert(1)"],
    ["chat"], // relative, not a path
    [" /chat"],
  ])("refuses %s and falls back to the chat", (next) => {
    expect(safeNext(next)).toBe("/chat");
  });
});

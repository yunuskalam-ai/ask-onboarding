import { describe, expect, it } from "vitest";
import { GITHUB, headingId, resolveImage, resolveLink, resolveRepoPath } from "./docsLinks";

const DOCS = [
  { slug: "readme", path: "README.md" },
  { slug: "architecture", path: "ARCHITECTURE.md" },
  { slug: "deploy", path: "deploy/README.md" },
];

describe("resolveRepoPath", () => {
  it.each([
    ["README.md", "ARCHITECTURE.md", "ARCHITECTURE.md"],
    ["deploy/README.md", "setup.sh", "deploy/setup.sh"],
    ["deploy/README.md", "../README.md", "README.md"],
    ["README.md", "./backend/app/auth.py", "backend/app/auth.py"],
  ])("%s + %s = %s", (from, rel, expected) => expect(resolveRepoPath(from, rel)).toBe(expected));

  it("refuses to climb out of the repo", () => {
    expect(resolveRepoPath("README.md", "../../etc/passwd")).toBeNull();
  });
});

describe("resolveLink", () => {
  it("another doc opens in the app, keeping the section", () => {
    expect(resolveLink("ARCHITECTURE.md#5-quality", "README.md", DOCS)).toEqual({
      kind: "doc",
      to: "/project-docs/architecture#5-quality",
    });
    expect(resolveLink("../README.md", "deploy/README.md", DOCS)).toEqual({ kind: "doc", to: "/project-docs/readme" });
  });

  it("a code file opens on GitHub", () => {
    expect(resolveLink("backend/app/auth.py", "README.md", DOCS)).toEqual({
      kind: "external",
      to: `${GITHUB}backend/app/auth.py`,
    });
    expect(resolveLink("setup.sh", "deploy/README.md", DOCS)).toEqual({ kind: "external", to: `${GITHUB}deploy/setup.sh` });
  });

  it("web links and in-page anchors pass through", () => {
    expect(resolveLink("https://sslip.io", "README.md", DOCS)).toEqual({ kind: "external", to: "https://sslip.io" });
    expect(resolveLink("#evaluation", "README.md", DOCS)).toEqual({ kind: "anchor", to: "#evaluation" });
  });

  it.each([
    ["javascript:alert(1)"],
    ["JAVASCRIPT:alert(1)"],
    ["data:text/html,<script>alert(1)</script>"],
    ["//evil.example/x"],
    ["vbscript:msgbox"],
    ["../../../etc/passwd"],
    [undefined],
  ])("%s is not followed", (href) => {
    expect(resolveLink(href, "README.md", DOCS)).toEqual({ kind: "none" });
  });
});

describe("resolveImage", () => {
  it("images in docs/ come from the API", () => {
    expect(resolveImage("docs/chat-citation.png", "README.md")).toBe("/api/admin/docs/assets/chat-citation.png");
    expect(resolveImage("../docs/architecture.svg", "deploy/README.md")).toBe("/api/admin/docs/assets/architecture.svg");
  });

  it.each([
    ["https://evil.example/x.png"],
    ["data:image/png;base64,AAAA"],
    ["docs/../.env"],
    ["sample_docs/handbook.pdf"],
    ["docs/sub/x.png"],
    ["docs/X.PNG"],
  ])("%s is not loaded", (src) => {
    expect(resolveImage(src, "README.md")).toBeNull();
  });
});

describe("headingId", () => {
  it.each([
    ["2. Choices, and what didn't work", "2-choices-and-what-didnt-work"],
    ["Quick start", "quick-start"],
    ["RAG vs. fine-tuning", "rag-vs-fine-tuning"],
  ])("%s -> %s", (text, id) => expect(headingId(text)).toBe(id));
});

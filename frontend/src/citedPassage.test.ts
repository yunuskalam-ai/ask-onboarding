import type { Element, Root } from "hast";
import { describe, expect, it } from "vitest";
import { END, START, markPassage, rehypeCitedPassage } from "./citedPassage";

describe("markPassage", () => {
  const show = (s: string) => s.replace(START, "[").replace(END, "]");

  it("wraps a passage in the middle of a line", () => {
    expect(show(markPassage("You get 25 days.", 8, 15))).toBe("You get [25 days].");
  });

  it.each([
    ["## Annual leave\n\nText", "## [Annual leave\n\nText]"],
    ["- Full-time: 25 days", "- [Full-time: 25 days]"],
    ["12. Step twelve", "12. [Step twelve]"],
    ["> A quote", "> [A quote]"],
    ["| YKLabs-Guest | Visitors |", "| [YKLabs-Guest | Visitors |]"],
  ])("keeps the line prefix in front: %s", (text, expected) => {
    expect(show(markPassage(text, 0, text.length))).toBe(expected);
  });

  it("a passage that is only a prefix still gets both markers", () => {
    expect(show(markPassage("## ", 0, 3))).toBe("## []");
  });
});

describe("rehypeCitedPassage", () => {
  const p = (text: string): Element => ({ type: "element", tagName: "p", properties: {}, children: [{ type: "text", value: text }] });

  it("marks the passage and tags every block it touches, across blocks", () => {
    const tree: Root = { type: "root", children: [p(`before ${START}cited one`), p(`cited two${END} after`), p("not cited")] };
    rehypeCitedPassage()(tree);
    const [first, second, third] = tree.children as Element[];

    expect(first.properties.className).toEqual(["cited"]);
    expect(first.children).toEqual([
      { type: "text", value: "before " },
      { type: "element", tagName: "mark", properties: {}, children: [{ type: "text", value: "cited one" }] },
    ]);
    expect(second.properties.className).toEqual(["cited"]);
    expect(third.properties.className).toBeUndefined();
    expect(JSON.stringify(tree)).not.toContain(START); // no marker characters left
  });

  it("works inside nested inline elements such as bold text", () => {
    const strong: Element = { type: "element", tagName: "strong", properties: {}, children: [{ type: "text", value: `${START}25 days${END}` }] };
    const tree: Root = { type: "root", children: [{ type: "element", tagName: "li", properties: {}, children: [strong] }] };
    rehypeCitedPassage()(tree);
    const li = tree.children[0] as Element;
    expect(li.properties.className).toEqual(["cited"]);
    expect((strong.children[0] as Element).tagName).toBe("mark");
  });
});

import { describe, expect, it } from "vitest";
import { answerParts } from "./answerParts";

describe("answerParts", () => {
  it("splits citations and bold text out of an answer", () => {
    expect(answerParts("You get **25 days** of leave [1][2].")).toEqual([
      { kind: "text", text: "You get " },
      { kind: "bold", text: "25 days" },
      { kind: "text", text: " of leave " },
      { kind: "cite", n: 1 },
      { kind: "cite", n: 2 },
      { kind: "text", text: "." },
    ]);
  });

  it("keeps HTML as plain text", () => {
    expect(answerParts("<img src=x onerror=alert(1)>")).toEqual([
      { kind: "text", text: "<img src=x onerror=alert(1)>" },
    ]);
  });

  it("leaves unmatched markers alone", () => {
    expect(answerParts("a ** b [x]")).toEqual([{ kind: "text", text: "a ** b [x]" }]);
  });
});

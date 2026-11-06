import { describe, expect, it } from "vitest";
import { createSseParser, type SseEvent } from "./sse";

function collect() {
  const events: SseEvent[] = [];
  return { events, feed: createSseParser((e) => events.push(e)) };
}

describe("createSseParser", () => {
  it("parses complete events", () => {
    const { events, feed } = collect();
    feed('event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n');
    expect(events).toEqual([
      { event: "token", data: '{"text":"Hi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("waits for the rest of an event split across network chunks", () => {
    const { events, feed } = collect();
    feed("event: tok");
    feed('en\ndata: {"text":');
    expect(events).toEqual([]);
    feed('"25 days"}\n');
    expect(events).toEqual([]);
    feed("\n");
    expect(events).toEqual([{ event: "token", data: '{"text":"25 days"}' }]);
  });

  it("accepts Windows line endings", () => {
    const { events, feed } = collect();
    feed("event: done\r\ndata: {}\r\n\r\n");
    expect(events).toEqual([{ event: "done", data: "{}" }]);
  });

  it("ignores blocks without data", () => {
    const { events, feed } = collect();
    feed(": keep-alive comment\n\n");
    expect(events).toEqual([]);
  });
});

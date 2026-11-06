// Parser for Server-Sent Events arriving in arbitrary pieces.
//
// The browser's EventSource only supports GET, and /api/chat is a POST,
// so we read the response body ourselves. A network chunk can end in the
// middle of an event, so we buffer until we see the blank line that ends it.

export type SseEvent = { event: string; data: string };

export function createSseParser(onEvent: (e: SseEvent) => void) {
  let buffer = "";

  return function feed(chunk: string) {
    buffer += chunk.replace(/\r\n/g, "\n");
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);

      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) onEvent({ event, data: data.join("\n") });
    }
  };
}

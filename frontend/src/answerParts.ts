// Split an answer into plain text, **bold** text and [n] citation markers,
// so it can be rendered without innerHTML (no HTML injection from the model).

export type Part =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "cite"; n: number };

const TOKEN = /(\[\d+\]|\*\*[^*]+\*\*)/g;

export function answerParts(answer: string): Part[] {
  const parts: Part[] = [];
  for (const piece of answer.split(TOKEN)) {
    if (!piece) continue;
    const cite = piece.match(/^\[(\d+)\]$/);
    if (cite) parts.push({ kind: "cite", n: Number(cite[1]) });
    else if (piece.startsWith("**") && piece.endsWith("**") && piece.length > 4)
      parts.push({ kind: "bold", text: piece.slice(2, -2) });
    else parts.push({ kind: "text", text: piece });
  }
  return parts;
}

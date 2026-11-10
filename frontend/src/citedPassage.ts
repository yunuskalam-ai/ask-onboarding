// Show a cited passage inside a formatted Markdown document.
//
// The citation is a character range in the raw Markdown. Two private-use
// characters mark its start and end in the text; after react-markdown has
// parsed the document, rehypeCitedPassage turns everything between them into
// <mark> and tags each paragraph, list item, heading or cell it touches with
// the "cited" class, so the passage shows as clean blocks.

import type { Element, ElementContent, Root, RootContent, Text } from "hast";

export const START = "";
export const END = "";

// Line prefixes that must stay at the start of a line for Markdown to read them.
const BLOCK_PREFIX = /^(#{1,6} +|[-*+] +|\d+[.)] +|> *|\| *)/;

/** The Markdown with START/END around [start, end). A start at a heading, bullet,
 *  numbered item, quote or table row moves past that prefix, so the line keeps
 *  its meaning. */
export function markPassage(text: string, start: number, end: number): string {
  const prefix = BLOCK_PREFIX.exec(text.slice(start, end));
  const from = prefix ? start + prefix[0].length : start; // the prefix is inside the passage
  return text.slice(0, from) + START + text.slice(from, end) + END + text.slice(end);
}

const BLOCKS = new Set(["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "blockquote", "pre"]);

/** A rehype plugin: markers -> <mark>, with the enclosing blocks tagged "cited". */
export function rehypeCitedPassage() {
  return (tree: Root) => {
    let inside = false;

    const visit = (node: Root | Element, block: Element | null) => {
      const out: RootContent[] = [];
      for (const child of node.children) {
        if (child.type === "text") {
          out.push(...split(child, block));
        } else {
          if (child.type === "element") visit(child, BLOCKS.has(child.tagName) ? child : block);
          out.push(child);
        }
      }
      node.children = out as Element["children"];
    };

    const split = (text: Text, block: Element | null): ElementContent[] => {
      const pieces: ElementContent[] = [];
      let buffer = "";
      const flush = () => {
        if (!buffer) return;
        if (inside) {
          pieces.push({ type: "element", tagName: "mark", properties: {}, children: [{ type: "text", value: buffer }] });
          if (block) block.properties = { ...block.properties, className: ["cited"] };
        } else {
          pieces.push({ type: "text", value: buffer });
        }
        buffer = "";
      };
      for (const ch of text.value) {
        if (ch === START || ch === END) {
          flush();
          inside = ch === START;
        } else {
          buffer += ch;
        }
      }
      flush();
      return pieces;
    };

    visit(tree, null);
  };
}

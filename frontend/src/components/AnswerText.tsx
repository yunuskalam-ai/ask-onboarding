import { answerParts } from "../answerParts";
import type { Citation } from "../api";

type Props = {
  text: string;
  citations: Citation[];
  onCite: (citation: Citation) => void;
};

/** An answer with its [n] markers turned into buttons that open the source. */
export default function AnswerText({ text, citations, onCite }: Props) {
  return (
    <>
      {answerParts(text).map((part, i) => {
        if (part.kind === "bold") return <strong key={i}>{part.text}</strong>;
        if (part.kind === "text") return <span key={i}>{part.text}</span>;

        const citation = citations.find((c) => c.n === part.n);
        // While streaming, citations are not known yet: show the marker as plain text.
        if (!citation) return <span key={i}>[{part.n}]</span>;
        return (
          <button
            key={i}
            className="cite"
            title={`${citation.filename}${citation.page ? `, page ${citation.page}` : ""}`}
            onClick={() => onCite(citation)}
          >
            {part.n}
          </button>
        );
      })}
    </>
  );
}

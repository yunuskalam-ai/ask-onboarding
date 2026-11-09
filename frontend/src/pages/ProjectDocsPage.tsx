import { Children, isValidElement, useEffect, useState, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import { Link, NavLink, useLocation, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { ApiError, getProjectDoc, listProjectDocs, type ProjectDoc, type ProjectDocSummary } from "../api";
import { GITHUB, headingId, resolveImage, resolveLink } from "../docsLinks";

/** The plain text of a heading, for its id. */
function textOf(children: ReactNode): string {
  return Children.toArray(children)
    .map((c) => (typeof c === "string" || typeof c === "number" ? String(c) : isValidElement(c) ? textOf((c.props as { children?: ReactNode }).children) : ""))
    .join("");
}

function components(doc: ProjectDoc, all: ProjectDocSummary[]): Components {
  const heading =
    (Tag: "h1" | "h2" | "h3" | "h4") =>
    ({ children }: { children?: ReactNode }) => <Tag id={headingId(textOf(children))}>{children}</Tag>;
  return {
    h1: heading("h1"),
    h2: heading("h2"),
    h3: heading("h3"),
    h4: heading("h4"),
    a: ({ href, children }) => {
      const link = resolveLink(href, doc.path, all);
      if (link.kind === "doc") return <Link to={link.to}>{children}</Link>;
      if (link.kind === "anchor") return <a href={link.to}>{children}</a>;
      if (link.kind === "external")
        return (
          <a href={link.to} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        );
      return <span>{children}</span>;
    },
    img: ({ src, alt }) => {
      const url = resolveImage(typeof src === "string" ? src : undefined, doc.path);
      return url ? <img src={url} alt={alt ?? ""} loading="lazy" /> : <span className="muted">[{alt || "image"}]</span>;
    },
    table: ({ children }) => (
      <div className="table-scroll">
        <table>{children}</table>
      </div>
    ),
  };
}

/** Admins: the project's documentation, full width, with working links between documents. */
export default function ProjectDocsPage() {
  const { slug = "guide" } = useParams();
  const { hash } = useLocation();
  const [list, setList] = useState<ProjectDocSummary[] | null>(null);
  const [doc, setDoc] = useState<ProjectDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjectDocs()
      .then(setList)
      .catch(() => setList([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    getProjectDoc(slug)
      .then((d) => !cancelled && (setDoc(d), setError(null)))
      .catch((err) => !cancelled && (setDoc(null), setError(err instanceof ApiError ? err.message : "Could not load it.")));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Jump to the section in the address (#...) once the document is on screen, or to the top.
  useEffect(() => {
    if (!doc) return;
    const target = hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
    if (target) target.scrollIntoView({ block: "start" });
    else window.scrollTo({ top: 0 });
  }, [doc, hash]);

  return (
    <div className="docs-layout">
      <aside className="docs-nav" aria-label="Documents">
        <strong>Project docs</strong>
        <ul>
          {list?.map((d) => (
            <li key={d.slug}>
              {d.available ? (
                <NavLink to={`/project-docs/${d.slug}`}>{d.title}</NavLink>
              ) : (
                <span className="muted" title={`${d.path} is not on this server`}>
                  {d.title}
                </span>
              )}
            </li>
          ))}
        </ul>
        {doc && (
          <a className="small" href={GITHUB + doc.path} target="_blank" rel="noopener noreferrer">
            View {doc.path} on GitHub
          </a>
        )}
      </aside>
      <article className="docs-body">
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {!doc && !error && <p className="muted">Loading…</p>}
        {doc && list && (
          <Markdown remarkPlugins={[remarkGfm]} components={components(doc, list)}>
            {doc.markdown}
          </Markdown>
        )}
      </article>
    </div>
  );
}

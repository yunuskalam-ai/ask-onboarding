// How links and images inside the project docs are resolved when they're shown
// in the app. The docs are written for GitHub, where "ARCHITECTURE.md" or
// "backend/app/auth.py" are relative links into the repo. In the app:
//   - a link to another listed doc opens it in the app (keeping any #section)
//   - a link to any other repo file opens it on GitHub, in a new tab
//   - an image in docs/ is loaded from the admin docs API
//   - anything else that isn't http(s) or an in-page #anchor is dropped

export const GITHUB = "https://github.com/yunuskalam-ai/ask-onboarding/blob/main/";

export type DocRef = { slug: string; path: string };

export type ResolvedLink =
  | { kind: "doc"; to: string } // in-app route
  | { kind: "anchor"; to: string } // #section on this page
  | { kind: "external"; to: string } // new tab
  | { kind: "none" }; // not followed

/** Join a relative path onto the folder of `from` (a repo path), resolving ".." and ".". */
export function resolveRepoPath(from: string, relative: string): string | null {
  const parts = from.split("/").slice(0, -1);
  for (const part of relative.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") {
      if (parts.length === 0) return null; // would leave the repo
      parts.pop();
    } else parts.push(part);
  }
  return parts.join("/");
}

export function resolveLink(href: string | undefined, currentPath: string, docs: DocRef[]): ResolvedLink {
  if (!href) return { kind: "none" };
  if (href.startsWith("#")) return { kind: "anchor", to: href };
  if (/^https?:\/\//i.test(href)) return { kind: "external", to: href };
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) return { kind: "none" }; // javascript:, data:, //host

  const [pathPart, hash = ""] = href.split("#", 2);
  const target = resolveRepoPath(currentPath, pathPart);
  if (target === null) return { kind: "none" };
  const doc = docs.find((d) => d.path === target);
  if (doc) return { kind: "doc", to: `/project-docs/${doc.slug}${hash ? `#${hash}` : ""}` };
  return { kind: "external", to: GITHUB + target + (hash ? `#${hash}` : "") };
}

/** An image from docs/ is served by the API; anything else isn't loaded (the CSP allows only this site). */
export function resolveImage(src: string | undefined, currentPath: string): string | null {
  if (!src || /^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//")) return null;
  const target = resolveRepoPath(currentPath, src);
  const match = target?.match(/^docs\/([a-z0-9][a-z0-9-]*\.(png|svg))$/);
  return match ? `/api/admin/docs/assets/${match[1]}` : null;
}

/** GitHub-style heading ids, so "#2-choices-and-what-didnt-work" links work in the app too. */
export function headingId(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s/g, "-");
}

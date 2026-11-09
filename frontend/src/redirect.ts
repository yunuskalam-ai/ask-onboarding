/**
 * Where to go after signing in, from the ?next= parameter. Only paths inside
 * this app are followed; anything else (another site, a protocol-relative
 * //host, javascript:, backslash tricks) falls back to the chat. This stops
 * a crafted sign-in link from sending someone to a look-alike site.
 */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/chat";
  // Resolve it the way the browser would and make sure it stays on this origin.
  const base = "http://app.invalid";
  try {
    const url = new URL(next, base);
    return url.origin === base ? url.pathname + url.search + url.hash : "/chat";
  } catch {
    return "/chat";
  }
}

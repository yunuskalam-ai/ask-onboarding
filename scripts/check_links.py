"""Check every relative link and #anchor in the project's Markdown files.

    python scripts/check_links.py

A link to a file must point at a file that exists; a link with #section must
point at a heading that exists in the target (GitHub's heading-id rules).
Web links (http/https) are not fetched. Exits 1 if anything is broken.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ["README.md", "ARCHITECTURE.md", "TECHNICAL.md", "GUIDE.md", "TESTING.md", "AI_LOG.md", "deploy/README.md"]

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*```")


def heading_ids(path: Path) -> set[str]:
    """GitHub-style ids: lowercase, drop punctuation except - and _, spaces to -."""
    ids, seen, in_code = set(), {}, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_code = not in_code
            continue
        match = None if in_code else HEADING.match(line)
        if not match:
            continue
        text = re.sub(r"`|\*\*?|__?", "", match.group(1))
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [text](link) -> text
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        ids.add(slug if n == 0 else f"{slug}-{n}")
    return ids


def links(path: Path) -> list[tuple[int, str]]:
    found, in_code = [], False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line):
            in_code = not in_code
            continue
        if not in_code:
            line = re.sub(r"`[^`]*`", "", line)  # links inside `code` aren't links
            found += [(number, href) for href in LINK.findall(line)]
    return found


def main() -> int:
    problems = []
    for doc in DOCS:
        source = ROOT / doc
        if not source.is_file():
            problems.append(f"{doc}: the document itself is missing")
            continue
        for line, href in links(source):
            if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
                continue  # http(s), mailto: not checked here
            target_part, _, anchor = href.partition("#")
            target = (source.parent / target_part).resolve() if target_part else source
            if not target.exists():
                problems.append(f"{doc}:{line}: {href} -> no such file")
            elif anchor and target.suffix == ".md" and anchor not in heading_ids(target):
                problems.append(f"{doc}:{line}: {href} -> no heading #{anchor} in {target.relative_to(ROOT)}")
    for p in problems:
        print(p)
    print(f"{len(problems)} broken links" if problems else "All links and anchors resolve.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

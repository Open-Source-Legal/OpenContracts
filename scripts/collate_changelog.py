#!/usr/bin/env python3
"""Collate per-PR changelog fragments into CHANGELOG.md.

Background
----------
Every PR used to edit the top of ``CHANGELOG.md``'s ``## [Unreleased]`` section,
so concurrent PRs collided on the same lines and produced perpetual merge
conflicts. Instead, each PR now drops a uniquely-named *fragment* in
``changelog.d/`` (see ``changelog.d/README.md``). Unique filenames mean PRs
never touch the same lines, so changelog conflicts become impossible.

This script turns those fragments into changelog prose:

    python scripts/collate_changelog.py --check     # validate fragments (CI)
    python scripts/collate_changelog.py --preview    # print collated markdown
    python scripts/collate_changelog.py --apply      # fold into CHANGELOG.md
                                                      # and delete fragments

``--apply`` merges the fragments into the existing ``## [Unreleased]`` section,
grouping everything by category in Keep-a-Changelog order. It does NOT cut a
version — renaming ``[Unreleased]`` to ``[X.Y.Z]`` and opening a fresh empty
``[Unreleased]`` stays a deliberate manual release step.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Keep a Changelog category order. Filenames use the lowercase key; the rendered
# section header uses the title-cased value.
CATEGORIES: dict[str, str] = {
    "added": "Added",
    "changed": "Changed",
    "deprecated": "Deprecated",
    "removed": "Removed",
    "fixed": "Fixed",
    "security": "Security",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_DIR = REPO_ROOT / "changelog.d"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# Fragment filenames look like "<slug>.<type>.md"; README.md is ignored.
FRAGMENT_RE = re.compile(r"^(?P<slug>.+)\.(?P<type>[a-zA-Z]+)\.md$")


class FragmentError(Exception):
    """A fragment file is malformed (bad type suffix or empty body)."""


def discover_fragments() -> list[Path]:
    """Return fragment files in changelog.d/, excluding README.md."""
    if not FRAGMENT_DIR.is_dir():
        return []
    return sorted(
        p
        for p in FRAGMENT_DIR.iterdir()
        if p.is_file() and p.name.lower() != "readme.md"
    )


def parse_fragment(path: Path) -> tuple[str, str]:
    """Return (category_key, body_text) for one fragment, validating it.

    Raises FragmentError if the filename has no valid ``.<type>.md`` suffix or
    the body is empty.
    """
    match = FRAGMENT_RE.match(path.name)
    if not match:
        raise FragmentError(
            f"{path.name}: name must be '<slug>.<type>.md' where <type> is one "
            f"of {', '.join(CATEGORIES)}"
        )
    category = match.group("type").lower()
    if category not in CATEGORIES:
        raise FragmentError(
            f"{path.name}: unknown type '{match.group('type')}'. "
            f"Use one of: {', '.join(CATEGORIES)}"
        )
    body = path.read_text(encoding="utf-8").strip()
    if not body:
        raise FragmentError(f"{path.name}: fragment body is empty")
    return category, body


def collect(fragments: list[Path]) -> dict[str, list[str]]:
    """Group fragment bodies by category, preserving filename sort order."""
    grouped: dict[str, list[str]] = {key: [] for key in CATEGORIES}
    errors: list[str] = []
    for path in fragments:
        try:
            category, body = parse_fragment(path)
        except FragmentError as exc:
            errors.append(str(exc))
            continue
        grouped[category].append(body)
    if errors:
        raise FragmentError("\n".join(errors))
    return grouped


def render(grouped: dict[str, list[str]]) -> str:
    """Render grouped fragment bodies as Keep-a-Changelog markdown."""
    blocks: list[str] = []
    for key, header in CATEGORIES.items():
        entries = grouped.get(key) or []
        if not entries:
            continue
        blocks.append(f"### {header}\n\n" + "\n".join(entries))
    return "\n\n".join(blocks)


def _split_unreleased(text: str) -> tuple[str, str, str]:
    """Split CHANGELOG into (before, unreleased_body, after).

    ``unreleased_body`` is everything between the ``## [Unreleased]`` header and
    the next ``## [`` header. Raises ValueError if no Unreleased header exists.
    """
    header_re = re.compile(r"^## \[Unreleased\][^\n]*$", re.MULTILINE)
    header = header_re.search(text)
    if not header:
        raise ValueError("No '## [Unreleased]' header found in CHANGELOG.md")
    body_start = header.end()
    next_section = re.compile(r"^## \[", re.MULTILINE).search(text, body_start)
    body_end = next_section.start() if next_section else len(text)
    return text[:body_start], text[body_start:body_end], text[body_end:]


def apply_to_changelog(grouped: dict[str, list[str]]) -> int:
    """Insert fragments into CHANGELOG.md's Unreleased section. Returns count.

    Surgical and lossless: existing Unreleased prose is never reparsed or
    re-rendered. For each category with fragments we either insert the new
    entries directly beneath the existing ``### <Header>`` line (top of that
    group) or, if no such header exists yet, prepend a fresh group at the top of
    the Unreleased body. Every other byte of the file is left exactly as-is.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    before, body, after = _split_unreleased(text)

    # Insert new-group blocks (for categories with no existing header) at the
    # very top of the Unreleased body, in canonical order.
    new_groups: list[str] = []
    for key, header in CATEGORIES.items():
        entries = grouped.get(key) or []
        if not entries:
            continue
        joined = "\n".join(entries)
        # Match an existing "### Header" line that is exactly this category
        # (avoid matching "### Technical Details" etc.).
        header_re = re.compile(rf"^### {re.escape(header)}\s*$", re.MULTILINE)
        existing_header = header_re.search(body)
        if existing_header:
            insert_at = existing_header.end()
            body = body[:insert_at] + "\n\n" + joined + body[insert_at:]
        else:
            new_groups.append(f"### {header}\n\n{joined}")

    if new_groups:
        body = "\n\n" + "\n\n".join(new_groups) + "\n" + body

    CHANGELOG.write_text(before + body + after, encoding="utf-8")
    return sum(len(v) for v in grouped.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        action="store_true",
        help="Validate fragment names/contents; exit nonzero on any problem.",
    )
    group.add_argument(
        "--preview",
        action="store_true",
        help="Print the collated markdown to stdout without modifying anything.",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Fold fragments into CHANGELOG.md's [Unreleased] section and "
        "delete the fragment files.",
    )
    args = parser.parse_args(argv)

    fragments = discover_fragments()

    if args.check:
        try:
            collect(fragments)
        except FragmentError as exc:
            print("Invalid changelog fragment(s):\n" + str(exc), file=sys.stderr)
            return 1
        print(f"OK: {len(fragments)} changelog fragment(s) valid.")
        return 0

    if not fragments:
        print("No changelog fragments in changelog.d/.", file=sys.stderr)
        return 0

    try:
        grouped = collect(fragments)
    except FragmentError as exc:
        print("Invalid changelog fragment(s):\n" + str(exc), file=sys.stderr)
        return 1

    if args.preview:
        print(render(grouped))
        return 0

    # --apply
    count = apply_to_changelog(grouped)
    for path in fragments:
        path.unlink()
    print(f"Folded {count} fragment(s) into {CHANGELOG.name} and removed them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

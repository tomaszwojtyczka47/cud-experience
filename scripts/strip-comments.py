#!/usr/bin/env python3
"""
Remove code comments from every file the browser receives, so nothing written
as a note to the developer shows up in DevTools (Elements or Sources).

Covers the served page code only:
  - every *.html page            -> <!-- ... --> comments
  - assets/**/*.css              -> /* ... */ comments
  - assets/**/*.js               -> // ... and /* ... */ comments

Not touched: text inside <script>/<style>/<textarea> blocks of a page (inline
code is left exactly as it is, because its sha256 is pinned in each page's CSP),
robots.txt / llms.txt / security.txt (plain text files with their own "#" syntax),
and scripts/, worker/ and .github/ (maintainer code that no page loads).

Usage:
  python3 scripts/strip-comments.py            remove the comments in place
  python3 scripts/strip-comments.py --check    list the comments, exit 1 if any
                                               (scripts/check-site-integrity.py
                                               runs this check in CI)

The journal block that scripts/sync-journal.py writes is found through its
data-journal-fallback element, so it needs no comment markers.

Stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

Range = tuple[int, int]


# --- Comment finders ----------------------------------------------------------
# Each returns the [start, end) ranges of the comments in a file, left to right.

HTML_TOKEN_RE = re.compile(
    r"<!--.*?-->|<(script|style|textarea)\b[^>]*>.*?</\1\s*>", re.S | re.I
)


def html_comments(src: str) -> list[Range]:
    """<!-- ... --> outside raw-text elements (their bodies are code or data, not markup)."""
    out = []
    for m in HTML_TOKEN_RE.finditer(src):
        if m.group(0).startswith("<!--"):
            out.append((m.start(), m.end()))
    return out


def css_comments(src: str) -> list[Range]:
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            i = _skip_string(src, i)
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise SystemExit("unterminated CSS comment")
            out.append((i, j + 2))
            i = j + 2
        elif src[i : i + 4].lower() == "url(":
            i += 4
            while i < n and src[i] in " \t\r\n":
                i += 1
            if i < n and src[i] not in "\"'":  # unquoted url(): up to the closing parenthesis
                j = src.find(")", i)
                i = n if j < 0 else j
        else:
            i += 1
    return out


def _skip_string(src: str, i: int) -> int:
    """Index just past the quoted string that opens at src[i]."""
    quote = src[i]
    i += 1
    n = len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
        elif src[i] == quote:
            return i + 1
        else:
            i += 1
    raise SystemExit("unterminated string")


JS_KEYWORDS_BEFORE_REGEX = {
    "return", "typeof", "case", "do", "else", "in", "of", "instanceof", "new", "delete",
    "void", "throw", "yield", "await",
}
JS_REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^}")


def js_comments(src: str) -> list[Range]:
    """// and /* */ comments, skipping strings, template literals and regex literals."""
    out: list[Range] = []
    n = len(src)

    def skip_regex(i: int) -> int:
        i += 1
        in_class = False
        while i < n:
            c = src[i]
            if c == "\\":
                i += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                i += 1
                while i < n and (src[i].isalnum() or src[i] in "_$"):
                    i += 1  # flags
                return i
            elif c == "\n":
                break
            i += 1
        raise SystemExit("unterminated regular expression")

    def skip_template(i: int) -> int:
        i += 1
        while i < n:
            c = src[i]
            if c == "\\":
                i += 2
            elif c == "`":
                return i + 1
            elif c == "$" and src[i + 1 : i + 2] == "{":
                i = scan(i + 2, nested=True)
            else:
                i += 1
        raise SystemExit("unterminated template literal")

    def scan(i: int, nested: bool) -> int:
        depth = 0
        prev = ""  # last significant token: a punctuation char, "word", or "val"
        word = ""
        while i < n:
            c = src[i]
            if c in " \t\r\n":
                i += 1
            elif c == "/" and src[i + 1 : i + 2] == "/":
                j = src.find("\n", i)
                j = n if j < 0 else j
                out.append((i, j))
                i = j
            elif c == "/" and src[i + 1 : i + 2] == "*":
                j = src.find("*/", i + 2)
                if j < 0:
                    raise SystemExit("unterminated block comment")
                out.append((i, j + 2))
                i = j + 2
            elif c == "/":
                if prev == "" or prev in JS_REGEX_AFTER or (prev == "word" and word in JS_KEYWORDS_BEFORE_REGEX):
                    i = skip_regex(i)
                    prev = "val"
                else:
                    i += 1
                    prev = "/"
            elif c in "\"'":
                i = _skip_string(src, i)
                prev = "val"
            elif c == "`":
                i = skip_template(i)
                prev = "val"
            elif c.isalpha() or c in "_$" or ord(c) > 127:
                j = i
                while j < n and (src[j].isalnum() or src[j] in "_$" or ord(src[j]) > 127):
                    j += 1
                word = src[i:j]
                prev = "word"
                i = j
            elif c.isdigit() or (c == "." and src[i + 1 : i + 2].isdigit()):
                j = i + 1
                while j < n and (src[j].isalnum() or src[j] in "._"):
                    if src[j] in "eE" and src[j + 1 : j + 2] in ("+", "-"):
                        j += 1
                    j += 1
                prev = "val"
                i = j
            else:
                if c == "{":
                    depth += 1
                elif c == "}":
                    if nested and depth == 0:
                        return i + 1
                    depth -= 1
                prev = c
                i += 1
        if nested:
            raise SystemExit("unterminated template substitution")
        return n

    scan(0, nested=False)
    return out


FINDERS = {".html": html_comments, ".css": css_comments, ".js": js_comments}


# --- Removing them -------------------------------------------------------------

def remove_ranges(src: str, ranges: list[Range], kind: str) -> str:
    """Cut the comments out, taking their own line (or the space around them) with them."""
    for a, b in reversed(ranges):
        line_start = src.rfind("\n", 0, a) + 1
        line_end = src.find("\n", b)
        line_end = len(src) if line_end < 0 else line_end
        before = src[line_start:a]
        after = src[b:line_end]
        if not before.strip() and not after.strip():
            # the comment is alone on its line(s): drop the lines, and one blank line if that
            # would leave two in a row
            cut_end = min(line_end + 1, len(src))
            if src[:line_start].endswith("\n\n") and src[cut_end:cut_end + 1] == "\n":
                cut_end += 1
            src = src[:line_start] + src[cut_end:]
        elif not after.strip():
            src = src[: a - (len(before) - len(before.rstrip(" \t")))] + src[b:]  # trailing comment
        elif not before.strip():
            src = src[:a] + src[b:].lstrip(" \t")  # comment in front of code
        else:
            left, right = src[a - 1], src[b]
            if kind == ".js" and "\n" in src[a:b]:
                joiner = "\n"  # a block comment spanning lines counts as a line break for ASI
            elif left in " \t" or right in " \t":
                joiner = ""
                if left in " \t" and right in " \t":
                    b += 1  # keep a single space
            else:
                joiner = "" if kind == ".html" else " "
            src = src[:a] + joiner + src[b:]
    return src


def served_files() -> list[Path]:
    files = [p for p in ROOT.rglob("*.html") if p.relative_to(ROOT).parts[0] not in (".git", "node_modules")]
    for ext in ("*.css", "*.js"):
        files += (ROOT / "assets").rglob(ext)
    return sorted(set(files))


def comments_in(path: Path) -> list[tuple[int, str]]:
    """(line number, first line of the comment) for each comment in a served file."""
    text = path.read_text(encoding="utf-8")
    found = []
    for a, b in FINDERS[path.suffix](text):
        found.append((text.count("\n", 0, a) + 1, text[a:b].strip().splitlines()[0][:80]))
    return found


def main(argv: list[str]) -> int:
    check = "--check" in argv
    total = 0
    for path in served_files():
        text = path.read_text(encoding="utf-8")
        ranges = FINDERS[path.suffix](text)
        if not ranges:
            continue
        total += len(ranges)
        rel = path.relative_to(ROOT)
        if check:
            print(f"{rel}: {len(ranges)} comment(s), first at line {text.count(chr(10), 0, ranges[0][0]) + 1}")
            continue
        path.write_text(remove_ranges(text, ranges, path.suffix), encoding="utf-8")
        print(f"{rel}: removed {len(ranges)} comment(s)")
    if check and total:
        print(f"FAILED: {total} comment(s) in served files; run python3 scripts/strip-comments.py")
        return 1
    print(f"{'Found' if check else 'Removed'} {total} comment(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

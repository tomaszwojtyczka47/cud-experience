#!/usr/bin/env python3
"""Keep the site navbar and its "Experiences" dropdown identical on every page.

Two kinds of navbar exist:

* HERO navbar (white text on a photo): the home pages and the Hoi An page. It is
  written by hand in the HTML; this script only keeps its "Experiences" dropdown
  in sync.
* LIGHT navbar (class "cud-nav cud-nav-lt", ink text on the sand background): every
  other page (About, Philosophy, Journal, Contact, Experiences, the Hoi An
  application and thank-you pages, Privacy, Terms). Same logo, links, language
  switch, Apply button, dropdown and hamburger as the home page. This script
  writes the whole thing, with links relative to each page, in front of <main>.
  Pages are recognised by that navbar; to give a new page one, copy the
  <nav class="cud-nav cud-nav-lt"> block from another page (and the hreflang links).

The dropdown rows are the experiences listed on /experiences/ and
/pl/experiences/, defined once in ROWS below.

  python3 scripts/sync-navbar.py           rewrite the pages
  python3 scripts/sync-navbar.py --check   exit 1 if any page is out of sync
                                            (also run by check-site-integrity.py)

When a trip goes live or its dates change: edit ROWS (and the experiences hub
page itself), run this script, commit the result.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name, meta (country / dates). Only Hoi An is bookable and linked for now.
ROWS = {
    "en": {
        "hoian": ("Hoi An", "Vietnam &middot; 20&ndash;30 Mar 2027"),
        "soon_label": "Coming soon",
        "soon": [("Bali", "Indonesia"), ("Surf &amp; Ride Bali", "Indonesia"), ("Kampot", "Cambodia")],
        "all": "All experiences",
    },
    "pl": {
        "hoian": ("Hoi An", "Wietnam &middot; 20&ndash;30 marca 2027"),
        "soon_label": "Wkr&oacute;tce",
        "soon": [("Bali", "Indonezja"), ("Surf &amp; Ride Bali", "Indonezja"), ("Kampot", "Kambod&#380;a")],
        "all": "Wszystkie do&#347;wiadczenia",
    },
}

# Navbar labels per language: (section dir, label). Experiences is the dropdown.
LABELS = {
    "en": {"aria": "Primary", "philosophy": "Philosophy", "journal": "Journal", "about": "About C.U.D.",
           "contact": "Contact", "apply": "Apply"},
    "pl": {"aria": "G&oacute;wna", "philosophy": "Filozofia", "journal": "Journal", "about": "O C.U.D.",
           "contact": "Kontakt", "apply": "Aplikuj"},
}

HERO_NAV_RE = re.compile(r'<nav class="cud-nav"[^>]*>.*?</nav>', re.S)
LIGHT_NAV_RE = re.compile(r'<nav class="cud-nav cud-nav-lt"[^>]*>.*?</nav>\n', re.S)
ITEM_RE = re.compile(
    r'<li(?: class="cud-has-sub")?><a href="([^"]*)"((?: aria-current="page")?)>Experiences</a>'
    r'(?:\n<div class="cud-sub">.*?</div>)?</li>',
    re.S,
)
LOGO_RE = re.compile(r'<svg class="cud-mark".*?</svg>', re.S)
HREFLANG_RE = re.compile(r'<link rel="alternate" hreflang="(en|pl)" href="https://cudexperience\.com/([^"]*)">')


def href_to(page_dir: str, target_dir: str) -> str:
    rel = os.path.relpath(target_dir or ".", page_dir or ".")
    return "./" if rel == "." else rel + "/"


def lang_of(rel_page: str) -> str:
    return "pl" if rel_page.startswith("pl/") else "en"


def dropdown_item(rel_page: str, link_href: str, link_attrs: str) -> str:
    lang = lang_of(rel_page)
    rows = ROWS[lang]
    page_dir = os.path.dirname(rel_page)
    hub_dir = "pl/experiences" if lang == "pl" else "experiences"
    hoian_dir = hub_dir + "/hoi-an"

    def cur(target: str) -> str:
        return ' aria-current="page"' if page_dir == target else ""

    name, meta = rows["hoian"]
    out = [
        f'<li class="cud-has-sub"><a href="{link_href}"{link_attrs}>Experiences</a>',
        '<div class="cud-sub">',
        f'<a class="cud-sub-row" href="{href_to(page_dir, hoian_dir)}"{cur(hoian_dir)}>'
        f'<span class="cud-sub-tx"><span class="cud-sub-name">{name}</span> <span class="cud-sub-meta">{meta}</span></span> '
        '<span class="cud-sub-go" aria-hidden="true"></span></a>',
    ]
    for name, meta in rows["soon"]:
        out.append(
            '<span class="cud-sub-row cud-sub-soon"><span class="cud-sub-tx">'
            f'<span class="cud-sub-name">{name}</span> <span class="cud-sub-meta">{meta}</span></span> '
            f'<span class="cud-sub-tag">{rows["soon_label"]}</span></span>'
        )
    out.append(
        f'<a class="cud-sub-row cud-sub-all" href="{href_to(page_dir, hub_dir)}"{cur(hub_dir)}>'
        f'<span class="cud-sub-name">{rows["all"]}</span> <span class="cud-sub-go" aria-hidden="true"></span></a>'
    )
    out.append("</div></li>")
    return "\n".join(out)


def logo_svg() -> str:
    m = LOGO_RE.search((ROOT / "index.html").read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("index.html: logo <svg class=\"cud-mark\"> not found")
    return m.group(0)


def alt_language_href(rel_page: str, text: str) -> str:
    lang = lang_of(rel_page)
    other = "pl" if lang == "en" else "en"
    found = dict(HREFLANG_RE.findall(text))
    if other not in found:
        raise SystemExit(f"{rel_page}: no hreflang={other} alternate to build the language switch from")
    return href_to(os.path.dirname(rel_page), found[other].rstrip("/"))


def light_navbar(rel_page: str, text: str, logo: str) -> str:
    lang = lang_of(rel_page)
    L = LABELS[lang]
    page_dir = os.path.dirname(rel_page)
    root = "pl/" if lang == "pl" else ""

    def link(section: str, label: str) -> str:
        target = root + section
        cur = ' aria-current="page"' if page_dir == target else ""
        return f'<li><a href="{href_to(page_dir, target)}"{cur}>{label}</a></li>'

    exp_dir = root + "experiences"
    exp_cur = ' aria-current="page"' if page_dir == exp_dir else ""
    alt = alt_language_href(rel_page, text)
    if lang == "en":
        lang_li = f'<li class="cud-lang"><span class="cud-lang-on">EN</span><span aria-hidden="true"> | </span><a href="{alt}">PL</a></li>'
    else:
        lang_li = f'<li class="cud-lang"><a href="{alt}">EN</a><span aria-hidden="true"> | </span><span class="cud-lang-on">PL</span></li>'
    return "\n".join([
        f'<nav class="cud-nav cud-nav-lt" aria-label="{L["aria"]}">',
        f'<a class="cud-logo cud-logo-h" href="{href_to(page_dir, root.rstrip("/"))}" aria-label="C.U.D. Experience">',
        logo,
        '<span class="cud-logo-bar"></span>',
        '<span class="cud-logo-tx"><span class="cud-logo-word">C.U.D.</span><span class="cud-logo-sub">Experience</span></span>',
        "</a>",
        "<ul>",
        dropdown_item(rel_page, href_to(page_dir, exp_dir), exp_cur),
        link("philosophy", L["philosophy"]),
        link("journal", L["journal"]),
        link("about", L["about"]),
        link("contact", L["contact"]),
        lang_li,
        f'<li><a class="on" href="{href_to(page_dir, root + "experiences/hoi-an/apply")}">{L["apply"]}</a></li>',
        "</ul>",
        '<button class="cud-menu-btn" type="button" aria-expanded="false" aria-label="Menu"><span aria-hidden="true"></span></button>',
        "</nav>",
        "",
    ])


def sync_page(path: Path, logo: str) -> tuple[str, str] | None:
    """Return (old, new) text for a page that has a navbar, else None."""
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(ROOT))
    new = text

    hero = HERO_NAV_RE.search(text)
    if hero:  # hand-written hero navbar: only keep its dropdown in sync
        block = hero.group(0)
        if len(ITEM_RE.findall(block)) != 1:
            raise SystemExit(f"{rel}: expected exactly one Experiences item in the navbar")
        block = ITEM_RE.sub(lambda m: dropdown_item(rel, m.group(1), m.group(2)), block)
        return text, text[: hero.start()] + block + text[hero.end():]

    if not LIGHT_NAV_RE.search(text):
        return None
    new = LIGHT_NAV_RE.sub("", new, count=1)  # rebuilt below
    main = re.search(r"<main[ >]", new)
    if not main:
        raise SystemExit(f"{rel}: no <main> to put the navbar in front of")
    new = new[: main.start()] + light_navbar(rel, text, logo) + new[main.start():]
    return text, new


def main() -> int:
    check = "--check" in sys.argv[1:]
    logo = logo_svg()
    stale = []
    for path in sorted(ROOT.rglob("*.html")):
        if ".git" in path.parts:
            continue
        res = sync_page(path, logo)
        if res is None:
            continue
        old, new = res
        if old != new:
            stale.append(str(path.relative_to(ROOT)))
            if not check:
                path.write_text(new, encoding="utf-8")
    if check:
        for rel in stale:
            print(f"{rel}: navbar is out of sync (run scripts/sync-navbar.py)")
        return 1 if stale else 0
    print(f"updated {len(stale)} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

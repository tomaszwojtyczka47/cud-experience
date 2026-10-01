#!/usr/bin/env python3
"""
Site integrity checker for cudexperience.com (static HTML site, no build step).

Checks, across every checked-in HTML page:

  1. sitemap.xml <lastmod> vs. each page's actual last-changed date in git.
  2. CSP <meta> script-src 'sha256-...' hashes vs. the real hashes of each
     page's inline <script> blocks (excluding application/ld+json, which
     CSP does not restrict, and non-inline scripts that carry a src=).
  3. Internal links/assets (href, src, srcset) resolve to a real file, and
     in-page #fragment links resolve to a real id= on the target page.
  4. EN/PL structural parity: every hreflang="en"/"pl" pair that the pages
     declare exists on both sides, and each pair's page carries roughly the
     same structural shape (image count, button count, form-field count,
     section/id count) so a section forgotten in translation gets flagged.

  5. JSON-LD structured data: every block parses, every {"@id": ...}
     reference resolves (on the same page or on the page it points at), WebPage
     urls / breadcrumbs match the canonical URL, and the Hoi An Event offers and
     FAQPage match what the page visibly says (prices, questions).
  6. robots.txt / llms.txt: robots.txt declares the sitemap and well-formed
     groups; llms.txt follows the llmstxt.org shape, its internal links resolve
     and every price it quotes appears on the Hoi An page.

Exit code is non-zero if any check finds a problem, so this is meant to run
in CI (see .github/workflows/site-integrity.yml).

No third-party dependencies - stdlib only.
"""
from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE_HOST = "cudexperience.com"

# Files that intentionally are not part of the site's directory-style page
# set (legacy no-JS redirect stubs, the 404 page) and so are exempt from the
# "every page is in the sitemap" check.
NON_SITEMAP_HTML = {"404.html", "privacy.html", "terms.html"}

# Extensions we don't try to resolve as pages/assets (external protocols are
# already filtered out separately).
SKIP_HREF_PREFIXES = ("http://", "https://", "mailto:", "tel:", "javascript:", "data:")

ROBOTS_NOINDEX_RE = re.compile(
    r'<meta\s+name="robots"\s+content="[^"]*noindex', re.IGNORECASE
)

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def all_html_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.html"):
        rel = p.relative_to(ROOT)
        parts = rel.parts
        if parts[0] in (".git", "node_modules"):
            continue
        out.append(p)
    return sorted(out)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. sitemap.xml <lastmod> vs. git history
# ---------------------------------------------------------------------------

def git_last_change_date(rel_path: str) -> str | None:
    """YYYY-MM-DD of the most recent commit touching rel_path, or None if
    the file has no commit history (e.g. newly added, uncommitted)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", rel_path],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None
    return out or None


def url_to_relpath(loc: str) -> str | None:
    parts = urlsplit(loc)
    if parts.netloc and parts.netloc != SITE_HOST:
        return None
    path = parts.path
    if path in ("", "/"):
        return "index.html"
    path = path.strip("/")
    return f"{path}/index.html"


def check_sitemap_lastmod() -> None:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        err("sitemap.xml missing")
        return
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tree = ET.parse(sitemap)
    seen_relpaths: set[str] = set()
    for url_el in tree.getroot().findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        lastmod_el = url_el.find("sm:lastmod", ns)
        if loc_el is None or loc_el.text is None:
            err("sitemap.xml: <url> with no <loc>")
            continue
        loc = loc_el.text.strip()
        rel = url_to_relpath(loc)
        if rel is None:
            warn(f"sitemap.xml: <loc>{loc}</loc> is off-host, skipping lastmod check")
            continue
        if not (ROOT / rel).exists():
            err(f"sitemap.xml: <loc>{loc}</loc> has no matching file ({rel})")
            continue
        seen_relpaths.add(rel)
        if lastmod_el is None or not lastmod_el.text:
            err(f"sitemap.xml: {loc} has no <lastmod>")
            continue
        lastmod = lastmod_el.text.strip()
        git_date = git_last_change_date(rel)
        if git_date is None:
            warn(f"sitemap.xml: {loc} ({rel}) has no git history yet, can't verify lastmod")
            continue
        if git_date > lastmod:
            err(
                f"sitemap.xml: {loc} <lastmod>{lastmod}</lastmod> is stale - "
                f"{rel} was last changed {git_date} in git. Bump <lastmod>."
            )

    # Every directory-style, indexable page (index.html) should be listed in
    # the sitemap. Pages marked noindex are intentionally left out of the
    # sitemap (Google's own guidance), so they're exempt.
    for p in all_html_files():
        rel = p.relative_to(ROOT).as_posix()
        if p.name != "index.html":
            if rel not in NON_SITEMAP_HTML and p.name not in NON_SITEMAP_HTML:
                warn(f"{rel}: non-index HTML file, not checked against sitemap")
            continue
        if ROBOTS_NOINDEX_RE.search(read(p)):
            if rel in seen_relpaths:
                err(f"{rel}: page is noindex but is listed in sitemap.xml (remove it)")
            continue
        if rel not in seen_relpaths:
            err(f"{rel}: page exists but is missing from sitemap.xml")


# ---------------------------------------------------------------------------
# 2. CSP sha256 hashes vs. actual inline <script> content
# ---------------------------------------------------------------------------

CSP_RE = re.compile(
    r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]*)"', re.IGNORECASE
)
SCRIPT_TAG_RE = re.compile(
    r'<script\b([^>]*)>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
ATTR_RE = re.compile(r'([a-zA-Z-]+)\s*=\s*"([^"]*)"')
SHA256_RE = re.compile(r"'sha256-([A-Za-z0-9+/=]+)'")


def csp_script_src_hashes(csp: str) -> set[str]:
    directives = {}
    for chunk in csp.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, *rest = chunk.split(None, 1)
        directives[name] = rest[0] if rest else ""
    script_src = directives.get("script-src", "")
    return set(SHA256_RE.findall(script_src))


def compute_inline_script_hashes(html_text: str) -> set[str]:
    # This site includes sha256 hashes for every inline <script> block, even
    # type="application/ld+json" ones - so every script without a src= needs
    # its hash present in the CSP, no type-based exemption.
    hashes = set()
    for attrs_raw, body in SCRIPT_TAG_RE.findall(html_text):
        attrs = dict((k.lower(), v) for k, v in ATTR_RE.findall(attrs_raw))
        if "src" in attrs:
            continue  # external script, no hash needed (allowed by host/self)
        digest = hashlib.sha256(body.encode("utf-8")).digest()
        hashes.add(base64.b64encode(digest).decode("ascii"))
    return hashes


def check_csp_hashes() -> None:
    for p in all_html_files():
        rel = str(p.relative_to(ROOT))
        text = read(p)
        csp_match = CSP_RE.search(text)
        if not csp_match:
            warn(f"{rel}: no CSP <meta> tag found, skipping hash check")
            continue
        csp = html.unescape(csp_match.group(1))
        declared = csp_script_src_hashes(csp)
        actual = compute_inline_script_hashes(text)
        missing = actual - declared
        unused = declared - actual
        for h in sorted(missing):
            err(f"{rel}: inline <script> hash 'sha256-{h}' is not in the CSP script-src (script will be blocked)")
        for h in sorted(unused):
            warn(f"{rel}: CSP declares 'sha256-{h}' but no inline <script> matches it (stale hash)")


# ---------------------------------------------------------------------------
# 3. Internal links / assets resolve, fragments resolve to a real id=
# ---------------------------------------------------------------------------

HREF_ATTR_RE = re.compile(r'\b(?:href|src)\s*=\s*"([^"]*)"', re.IGNORECASE)
SRCSET_ATTR_RE = re.compile(r'\bsrcset\s*=\s*"([^"]*)"', re.IGNORECASE)
ID_ATTR_RE = re.compile(r'\bid\s*=\s*"([^"]+)"', re.IGNORECASE)


def page_ids(html_text: str) -> set[str]:
    return set(ID_ATTR_RE.findall(html_text))


def resolve_local_path(rel_from: Path, target: str) -> Path | None:
    """target is a href/src value already stripped of query/fragment."""
    if target == "":
        return None
    if target.startswith("/"):
        candidate = ROOT / target.lstrip("/")
    else:
        candidate = (rel_from.parent / target).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None  # escapes the repo root
    return candidate


def resolve_page_or_asset(candidate: Path) -> Path | None:
    if candidate.is_dir():
        idx = candidate / "index.html"
        return idx if idx.exists() else None
    if candidate.exists():
        return candidate
    # directory-style URL without trailing slash content already implied by "/",
    # nothing else to try
    return None


def check_internal_links() -> None:
    id_cache: dict[Path, set[str]] = {}

    def ids_for(p: Path) -> set[str]:
        if p not in id_cache:
            id_cache[p] = page_ids(read(p)) if p.suffix == ".html" and p.exists() else set()
        return id_cache[p]

    for p in all_html_files():
        rel = str(p.relative_to(ROOT))
        text = read(p)
        my_ids = ids_for(p)

        targets: list[str] = []
        for m in HREF_ATTR_RE.finditer(text):
            targets.append(m.group(1))
        for m in SRCSET_ATTR_RE.finditer(text):
            for part in m.group(1).split(","):
                url = part.strip().split()[0] if part.strip() else ""
                if url:
                    targets.append(url)

        for raw in targets:
            target = html.unescape(raw.strip())
            if not target or target.startswith("#!"):
                continue
            if target.startswith(SKIP_HREF_PREFIXES):
                continue
            if target.startswith("https://cudexperience.com") or target.startswith("http://cudexperience.com"):
                # same-site absolute URL - still worth checking, strip host
                target = urlsplit(target).path or "/"

            frag = None
            path_part = target
            if "#" in path_part:
                path_part, frag = path_part.split("#", 1)
            if "?" in path_part:
                path_part = path_part.split("?", 1)[0]

            if path_part == "":
                # pure fragment link, e.g. href="#about"
                if frag and frag not in my_ids:
                    err(f"{rel}: fragment link '#{frag}' has no matching id= on this page")
                continue

            candidate = resolve_local_path(p, path_part)
            if candidate is None:
                err(f"{rel}: link target '{target}' escapes the site root or is malformed")
                continue
            resolved = resolve_page_or_asset(candidate)
            if resolved is None:
                err(f"{rel}: broken link/asset reference '{target}' -> no such file")
                continue
            if frag:
                target_ids = ids_for(resolved)
                if frag not in target_ids:
                    err(f"{rel}: link '{target}' points at fragment '#{frag}' with no matching id= in {resolved.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# 4. EN/PL parity
# ---------------------------------------------------------------------------

HREFLANG_RE = re.compile(
    r'<link\s+rel="alternate"\s+hreflang="(en|pl)"\s+href="([^"]*)"', re.IGNORECASE
)
IMG_RE = re.compile(r'<img\b', re.IGNORECASE)
BTN_RE = re.compile(r'class="[^"]*\bcud-btn\b', re.IGNORECASE)
INPUT_RE = re.compile(r'<(?:input|textarea|select)\b', re.IGNORECASE)
FORM_RE = re.compile(r'<form\b', re.IGNORECASE)


def structural_counts(html_text: str) -> dict[str, int]:
    return {
        "img": len(IMG_RE.findall(html_text)),
        "buttons": len(BTN_RE.findall(html_text)),
        "form_fields": len(INPUT_RE.findall(html_text)),
        "forms": len(FORM_RE.findall(html_text)),
        "ids": len(ID_ATTR_RE.findall(html_text)),
    }


def check_en_pl_parity() -> None:
    pairs: dict[str, dict[str, str]] = {}  # canonical key -> {"en": relpath, "pl": relpath}
    for p in all_html_files():
        rel = str(p.relative_to(ROOT))
        text = read(p)
        links = HREFLANG_RE.findall(text)
        if not links:
            continue
        by_lang = {lang: url_to_relpath(href) for lang, href in links}
        en_rel = by_lang.get("en")
        pl_rel = by_lang.get("pl")
        if en_rel is None and pl_rel is None:
            continue
        key = en_rel or pl_rel
        entry = pairs.setdefault(key, {})
        if en_rel:
            entry["en"] = en_rel
        if pl_rel:
            entry["pl"] = pl_rel

    checked: set[tuple[str, str]] = set()
    for key, entry in pairs.items():
        en_rel = entry.get("en")
        pl_rel = entry.get("pl")
        if en_rel is None or pl_rel is None:
            missing_lang = "pl" if en_rel else "en"
            err(f"{en_rel or pl_rel}: hreflang alternate for '{missing_lang}' not declared on either language's page")
            continue
        pair_key = (en_rel, pl_rel)
        if pair_key in checked:
            continue
        checked.add(pair_key)

        en_path = ROOT / en_rel
        pl_path = ROOT / pl_rel
        if not en_path.exists():
            err(f"{pl_rel}: hreflang points at '{en_rel}' which does not exist")
            continue
        if not pl_path.exists():
            err(f"{en_rel}: hreflang points at '{pl_rel}' which does not exist")
            continue

        en_counts = structural_counts(read(en_path))
        pl_counts = structural_counts(read(pl_path))
        for field, en_n in en_counts.items():
            pl_n = pl_counts[field]
            if en_n != pl_n:
                err(
                    f"EN/PL parity: {en_rel} has {en_n} {field} but {pl_rel} has {pl_n} "
                    f"- a section may be missing in translation"
                )


# ---------------------------------------------------------------------------
# 5. JSON-LD structured data
# ---------------------------------------------------------------------------

LD_BLOCK_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]*)"', re.IGNORECASE)
SPACE_PRICE_RE = re.compile(r'<p class="cud-space-price">(.*?)</p>', re.S)
FAQ_ITEM_RE = re.compile(r'<li class="cud-faq-item"><details><summary>(.*?)</summary>', re.S)


def rel_to_url(rel: str) -> str:
    if rel == "index.html":
        return f"https://{SITE_HOST}/"
    return f"https://{SITE_HOST}/{rel[: -len('index.html')]}"


def visible_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def walk_ld(node, defined: set[str], refs: list[str], nodes: list[dict]) -> None:
    if isinstance(node, list):
        for x in node:
            walk_ld(x, defined, refs, nodes)
    elif isinstance(node, dict):
        if "@id" in node and set(node) == {"@id"}:
            refs.append(node["@id"])
            return
        if "@id" in node:
            defined.add(node["@id"])
        if "@type" in node:
            nodes.append(node)
        for k, v in node.items():
            if k != "@context":
                walk_ld(v, defined, refs, nodes)


def check_jsonld() -> None:
    import json

    per_page: dict[str, dict] = {}
    for p in all_html_files():
        rel = p.relative_to(ROOT).as_posix()
        text = read(p)
        blocks = LD_BLOCK_RE.findall(text)
        if not blocks:
            continue
        defined: set[str] = set()
        refs: list[str] = []
        nodes: list[dict] = []
        ok = True
        for body in blocks:
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                err(f"{rel}: JSON-LD block is not valid JSON ({e})")
                ok = False
                continue
            walk_ld(data, defined, refs, nodes)
        if ok:
            per_page[rel] = {"defined": defined, "refs": refs, "nodes": nodes, "text": text}

    by_url = {rel_to_url(rel): info["defined"] for rel, info in per_page.items()}

    for rel, info in per_page.items():
        text, nodes = info["text"], info["nodes"]
        for ref in info["refs"]:
            if ref in info["defined"]:
                continue
            base = ref.split("#", 1)[0]
            if ref in by_url.get(base, set()):
                continue
            err(f"{rel}: JSON-LD reference '{ref}' is not defined on this page or on the page it points at")

        canon = CANONICAL_RE.search(text)
        canon_url = canon.group(1) if canon else None
        for n in nodes:
            types = n["@type"] if isinstance(n["@type"], list) else [n["@type"]]
            if "BreadcrumbList" in types:
                items = n.get("itemListElement", [])
                if [i.get("position") for i in items] != list(range(1, len(items) + 1)):
                    err(f"{rel}: BreadcrumbList positions are not 1..{len(items)}")
                if canon_url and items and items[-1].get("item") != canon_url:
                    err(f"{rel}: last BreadcrumbList item {items[-1].get('item')} is not the canonical URL")
            if any(t in ("WebPage", "AboutPage", "ContactPage", "CollectionPage") for t in types):
                if canon_url and n.get("url") != canon_url:
                    err(f"{rel}: WebPage url {n.get('url')} does not match canonical {canon_url}")
            if "Event" in types:
                for key in ("name", "startDate", "location"):
                    if key not in n:
                        err(f"{rel}: Event is missing '{key}'")
                offers = n.get("offers", [])
                for o in offers:
                    for key in ("price", "priceCurrency", "availability", "url", "validFrom"):
                        if key not in o:
                            err(f"{rel}: Event offer '{o.get('name')}' is missing '{key}'")
                visible = sorted(re.sub(r"\D", "", visible_text(re.sub(r"<span.*?</span>", "", m)))
                                 for m in SPACE_PRICE_RE.findall(text))
                declared = sorted(str(o.get("price")) for o in offers)
                if visible and visible != declared:
                    err(f"{rel}: Event offer prices {declared} differ from the visible room prices {visible}")
            if "FAQPage" in types:
                declared_q = [q.get("name") for q in n.get("mainEntity", [])]
                visible_q = [visible_text(q) for q in FAQ_ITEM_RE.findall(text)]
                if declared_q != visible_q:
                    err(f"{rel}: FAQPage questions do not match the visible FAQ ({len(declared_q)} vs {len(visible_q)})")


# ---------------------------------------------------------------------------
# 6. robots.txt and llms.txt
# ---------------------------------------------------------------------------

MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
PRICE_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")  # amounts written like 19,500
AI_BOTS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
           "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended")


def check_robots_txt() -> None:
    path = ROOT / "robots.txt"
    if not path.exists():
        err("robots.txt missing")
        return
    groups: list[tuple[list[str], list[str]]] = []  # (user-agents, rules)
    sitemaps: list[str] = []
    agents: list[str] = []
    rules: list[str] = []
    for raw in read(path).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (x.strip() for x in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value)
        elif field in ("allow", "disallow"):
            rules.append(f"{field}: {value}")
        elif field == "sitemap":
            sitemaps.append(value)
    if agents:
        groups.append((agents, rules))
    for ua, rl in groups:
        if not rl:
            err(f"robots.txt: group for {', '.join(ua)} has no Allow/Disallow rule")
    if not any("*" in ua for ua, _ in groups):
        err("robots.txt: no 'User-agent: *' group")
    if f"https://{SITE_HOST}/sitemap.xml" not in sitemaps:
        err(f"robots.txt: missing 'Sitemap: https://{SITE_HOST}/sitemap.xml'")
    for ua, rl in groups:
        for bot in ua:
            if bot in AI_BOTS and "disallow: /" in rl:
                warn(f"robots.txt: {bot} is disallowed from the whole site (intended?)")


def check_llms_txt() -> None:
    path = ROOT / "llms.txt"
    if not path.exists():
        err("llms.txt missing")
        return
    text = read(path)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("# "):
        err("llms.txt: must start with a single '# Title' H1 line")
    if len(lines) < 2 or not lines[1].startswith("> "):
        err("llms.txt: the H1 must be followed by a '> summary' blockquote")
    if sum(1 for ln in lines if ln.startswith("# ")) != 1:
        err("llms.txt: must contain exactly one H1")

    for raw in MD_LINK_RE.findall(text):
        target = raw
        if target.startswith(f"https://{SITE_HOST}"):
            target = urlsplit(target).path or "/"
        elif target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part = target.split("#", 1)[0].split("?", 1)[0]
        candidate = resolve_local_path(ROOT / "llms.txt", path_part)
        if candidate is None or resolve_page_or_asset(candidate) is None:
            err(f"llms.txt: link '{raw}' does not resolve to a file in the site")

    hoian = ROOT / "experiences" / "hoi-an" / "index.html"
    if hoian.exists():
        visible = {re.sub(r"\D", "", visible_text(m)) for m in SPACE_PRICE_RE.findall(read(hoian))}
        for price in PRICE_RE.findall(text):
            if re.sub(r"\D", "", price) not in visible:
                err(f"llms.txt: amount '{price}' does not match any price on the Hoi An page")


# ---------------------------------------------------------------------------
# 7. Journal static block (written by scripts/sync-journal.py)
# ---------------------------------------------------------------------------

JOURNAL_PAGES = ("journal/index.html", "pl/journal/index.html")
JOURNAL_START_RE = re.compile(r"<!-- journal-feed:start\b[^>]*-->")
JOURNAL_END = "<!-- journal-feed:end -->"
JOURNAL_CARD_RE = re.compile(r'<a class="cud-jrl-card" href="([^"]*)"([^>]*)>')


def check_journal_feed() -> None:
    """The pre-rendered Journal posts must stay a well-formed, safe block: the
    JS carousel hides it through data-journal-fallback, and every card must
    point at the blog (the feed text is third-party content)."""
    for rel in JOURNAL_PAGES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = read(path)
        starts = JOURNAL_START_RE.findall(text)
        if not starts and JOURNAL_END not in text:
            warn(f"{rel}: no pre-rendered Journal block (scripts/sync-journal.py has not run yet)")
            continue
        if len(starts) != 1 or text.count(JOURNAL_END) != 1:
            err(f"{rel}: expected exactly one journal-feed:start and one journal-feed:end marker")
            continue
        a = JOURNAL_START_RE.search(text).end()
        b = text.index(JOURNAL_END)
        if b < a:
            err(f"{rel}: journal-feed markers are in the wrong order")
            continue
        block = text[a:b]
        if block.count("data-journal-fallback") != 1:
            err(f"{rel}: Journal block must contain exactly one data-journal-fallback element")
        if block.count("<div") != block.count("</div>"):
            err(f"{rel}: unbalanced <div> inside the Journal block")
        cards = JOURNAL_CARD_RE.findall(block)
        if not cards:
            err(f"{rel}: Journal block has no post cards")
        for href, rest in cards:
            if not href.startswith("https://travelpixiefreak.com/"):
                err(f"{rel}: Journal card links outside travelpixiefreak.com: {href}")
            if "noopener" not in rest:
                err(f"{rel}: Journal card {href} opens a new tab without rel=noopener")


# ---------------------------------------------------------------------------

def main() -> int:
    check_sitemap_lastmod()
    check_csp_hashes()
    check_internal_links()
    check_en_pl_parity()
    check_jsonld()
    check_robots_txt()
    check_llms_txt()
    check_journal_feed()

    if warnings:
        print(f"--- {len(warnings)} warning(s) ---")
        for w in warnings:
            print(f"WARN: {w}")
    if errors:
        print(f"--- {len(errors)} error(s) ---")
        for e in errors:
            print(f"ERROR: {e}")
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"OK: 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Pre-render the latest Journal posts into the static HTML.

The Journal page shows a carousel that assets/js/journal-carousel.js fills at
runtime from /api/journal (worker/journal.js, which proxies the TravelPixieFreak
category feeds). Crawlers that do not run JavaScript, including most AI
crawlers, never saw those posts, only the static "First stories coming soon"
panel. This script fetches the same two feeds and writes the posts into the
page as the static fallback block, in the same card markup the carousel uses:

  - visitors with JavaScript see no difference (the script hides this block as
    soon as the carousel loads, exactly as it hid the old "coming soon" panel);
  - crawlers, no-JS visitors and visitors whose /api/journal request fails see
    the real latest posts (title, date, excerpt, link) and a link to the archive.

Each card also carries what the JSON-LD needs, all taken from the blog itself and
never guessed: the full publication timestamp (<time datetime>, from the feed's
pubDate), the author (feed dc:creator and the blog's author archive URL) and the
post's image (og:image of the post page, falling back to the first image of the
post in the feed). A field the blog does not provide is simply left out.

Then it refreshes the JSON-LD (scripts/generate-structured-data.py), which lists
the same posts, and bumps the sitemap <lastmod> of the pages that changed.

Safety: it never replaces a populated block with an empty one. If a feed cannot
be fetched or has no valid items, that language is left untouched (a warning is
printed, the exit code stays 0). Feed text is untrusted: every value is
HTML-escaped, and only links under https://travelpixiefreak.com/ are accepted.

Usage:  python3 scripts/sync-journal.py
Run daily by .github/workflows/journal-sync.yml. Stdlib only.
"""
from __future__ import annotations

import datetime
import email.utils
import html
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same sources as worker/journal.js (one WordPress category per language).
FEEDS = {
    "en": "https://travelpixiefreak.com/category/shades-of-human-life/feed/",
    "pl": "https://travelpixiefreak.com/category/odcienie-ludzkiego-zycia/feed/",
}
ARCHIVES = {
    "en": "https://travelpixiefreak.com/category/shades-of-human-life/",
    "pl": "https://travelpixiefreak.com/category/odcienie-ludzkiego-zycia/",
}
PAGES = {"en": "journal/index.html", "pl": "pl/journal/index.html"}
BLOG_PREFIX = "https://travelpixiefreak.com/"
MAX_ITEMS = 10  # the feeds' native size, and what the carousel shows
EXCERPT_CHARS = 140  # same cut as truncate() in assets/js/journal-carousel.js
USER_AGENT = "CUDExperienceJournalSync/1.0 (+https://cudexperience.com)"
UPLOADS_PREFIX = BLOG_PREFIX + "wp-content/uploads/"
AUTHOR_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")  # WordPress author archive: /author/<slug>/
MIN_IMAGE_SIDE = 200  # skip icons and spacers
POST_PAGE_DELAY = 0.3  # seconds between requests to the blog

STRINGS = {
    "en": {"read": "Read on TravelPixieFreak", "all": "All stories on TravelPixieFreak"},
    "pl": {"read": "Czytaj na TravelPixieFreak", "all": "Wszystkie historie na TravelPixieFreak"},
}
PL_MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
             "września", "października", "listopada", "grudnia"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]

# The generated block is the one <div ... data-journal-fallback> element on the page. It is found
# through that attribute (no comment markers: the site ships without HTML comments).
BLOCK_OPEN_RE = re.compile(r"<div\b[^>]*\bdata-journal-fallback\b[^>]*>")


def fetch(url: str, tries: int = 3) -> str | None:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # network errors, HTTP errors, bad encodings
            print(f"  fetch attempt {attempt + 1} failed for {url}: {exc}")
            if attempt + 1 < tries:
                time.sleep(2 * (attempt + 1))
    return None


def tag_value(block: str, tag: str) -> str:
    """Mirror tagValue() in worker/journal.js: strip CDATA, drop tags, decode entities."""
    m = re.search(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", block)
    if not m:
        return ""
    value = m.group(1).strip()
    cdata = re.match(r"^<!\[CDATA\[([\s\S]*)\]\]>$", value)
    if cdata:
        value = cdata.group(1)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def feed_image(block: str) -> dict | None:
    """First real photo of the post in the feed's full content (it can differ from the
    post's featured image, so it is only the fallback for og_image())."""
    m = re.search(r"<content:encoded>([\s\S]*?)</content:encoded>", block)
    if not m:
        return None
    body = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", m.group(1))
    for tag in re.findall(r"<img\b[^>]*>", body):
        src = re.search(r'\bsrc="([^"]*)"', tag)
        if not src:
            continue
        url = html.unescape(src.group(1))
        if not url.startswith(UPLOADS_PREFIX):
            continue
        dims = {}
        for attr in ("width", "height"):
            v = re.search(rf'\b{attr}="(\d+)"', tag)
            if v:
                dims[attr] = int(v.group(1))
        if dims.get("width", MIN_IMAGE_SIDE) < MIN_IMAGE_SIDE or dims.get("height", MIN_IMAGE_SIDE) < MIN_IMAGE_SIDE:
            continue
        return {"url": url, **dims}
    return None


def og_image(post_url: str) -> dict | None:
    """The post's own featured image, as the blog declares it in og:image."""
    page = fetch(post_url, tries=2)
    time.sleep(POST_PAGE_DELAY)
    if not page:
        return None
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', page)
    if not m:
        return None
    url = html.unescape(m.group(1))
    if not url.startswith(UPLOADS_PREFIX):
        return None
    image = {"url": url}
    for attr in ("width", "height"):
        v = re.search(rf'<meta\s+property="og:image:{attr}"\s+content="(\d+)"', page)
        if v:
            image[attr] = int(v.group(1))
    if image.get("width", MIN_IMAGE_SIDE) < MIN_IMAGE_SIDE or image.get("height", MIN_IMAGE_SIDE) < MIN_IMAGE_SIDE:
        return None
    return image


def parse_items(xml: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item>([\s\S]*?)</item>", xml):
        title = tag_value(block, "title")
        link = tag_value(block, "link")
        pub = tag_value(block, "pubDate")
        excerpt = tag_value(block, "description")
        creator = tag_value(block, "dc:creator")
        if not (title and link and link.startswith(BLOG_PREFIX)):
            continue
        try:
            stamp = email.utils.parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            stamp = None
        if stamp is not None and stamp.tzinfo is None:
            stamp = None  # a timestamp without a zone would be a guess
        items.append({
            "title": title, "link": link, "excerpt": excerpt, "creator": creator,
            "stamp": stamp,  # timezone-aware, exactly as the feed gives it
            "date": stamp.astimezone(datetime.timezone.utc).date() if stamp else None,
            "feed_image": feed_image(block),
        })
        if len(items) == MAX_ITEMS:
            break
    return items


def existing_images(page_text: str) -> dict[str, dict]:
    """Images already written to the page, keyed by post URL (reused if the blog is unreachable)."""
    found = {}
    for attrs in re.findall(r'<a class="cud-jrl-card"([^>]*)>', page_text):
        d = {k: html.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', attrs)}
        if d.get("href") and d.get("data-image"):
            img = {"url": d["data-image"]}
            for attr in ("width", "height"):
                if d.get(f"data-image-{attr}", "").isdigit():
                    img[attr] = int(d[f"data-image-{attr}"])
            found[d["href"]] = img
    return found


def attach_images(items: list[dict], page_text: str) -> None:
    previous = existing_images(page_text)
    for item in items:
        item["image"] = og_image(item["link"]) or previous.get(item["link"]) or item["feed_image"]


def truncate(text: str, n: int = EXCERPT_CHARS) -> str:
    text = text.strip()
    if len(text) <= n:
        return text
    cut = text[:n]
    last = cut.rfind(" ")
    return (cut[:last] if last > 40 else cut) + "…"


def fmt_date(date: datetime.date, lang: str) -> str:
    if lang == "pl":
        return f"{date.day} {PL_MONTHS[date.month - 1]} {date.year}"
    return f"{EN_MONTHS[date.month - 1]} {date.day}, {date.year}"


def esc(text: str) -> str:
    """HTML-escape and write non-ASCII as numeric references, like the rest of the site."""
    return html.escape(text, quote=True).encode("ascii", "xmlcharrefreplace").decode("ascii")


def author_url(name: str) -> str | None:
    """WordPress puts a user's posts at /author/<login>/. Only built for plain logins."""
    return f"{BLOG_PREFIX}author/{name}/" if AUTHOR_SLUG_RE.match(name) else None


def render_card(item: dict, lang: str) -> str:
    when = ""
    if item["date"]:
        when = f'<time datetime="{item["stamp"].isoformat()}">{esc(fmt_date(item["date"], lang))}</time>'
    extra = ""
    if item["creator"]:
        extra += f' data-author="{esc(item["creator"])}"'
        url = author_url(item["creator"])
        if url:
            extra += f' data-author-url="{esc(url)}"'
    image = item.get("image")
    if image:
        extra += f' data-image="{esc(image["url"])}"'
        for attr in ("width", "height"):
            if attr in image:
                extra += f' data-image-{attr}="{image[attr]}"'
    return (
        f'<a class="cud-jrl-card" href="{esc(item["link"])}" target="_blank" rel="noopener"{extra}>'
        f'<span class="cud-jrl-card-in"><span class="cud-jrl-date">{when}</span>'
        f'<span class="cud-jrl-h">{esc(" ".join(item["title"].split()))}</span>'
        f'<span class="cud-jrl-ex">{esc(" ".join(truncate(item["excerpt"]).split()))}</span>'
        f'<span class="cud-jrl-link">{esc(STRINGS[lang]["read"])} &rarr;</span></span></a>'
    )


def render_block(items: list[dict], lang: str) -> str:
    cards = "\n".join(render_card(i, lang) for i in items)
    return (
        '<div class="cud-jrl cud-reveal cud-reveal-3" data-journal-fallback>\n'
        f'<div class="cud-jrl-viewport"><div class="cud-jrl-track">\n{cards}\n</div></div>\n'
        f'<p class="cud-p cud-xh-more"><a class="cud-pv-link" href="{esc(ARCHIVES[lang])}" '
        f'target="_blank" rel="noopener">{esc(STRINGS[lang]["all"])} &rarr;</a></p>\n'
        "</div>"
    )


def div_end(text: str, start: int) -> int:
    """Index just past the </div> that closes the <div> opening at `start`."""
    depth = 0
    for m in re.finditer(r"<div\b|</div>", text[start:]):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth == 0:
            return start + m.end()
    raise SystemExit("unbalanced <div> in journal page")


def apply_block(text: str, block: str) -> str:
    opens = BLOCK_OPEN_RE.findall(text)
    if len(opens) != 1:
        raise SystemExit(f"journal page must contain exactly one data-journal-fallback element, found {len(opens)}")
    a = BLOCK_OPEN_RE.search(text).start()
    return text[:a] + block + text[div_end(text, a):]


def bump_lastmod(path_rel: str, today: str) -> None:
    sitemap = ROOT / "sitemap.xml"
    loc = "https://cudexperience.com/" + path_rel[: -len("index.html")]
    s = sitemap.read_text(encoding="utf-8")
    new = re.sub(rf"(<url><loc>{re.escape(loc)}</loc><lastmod>)[^<]+(</lastmod>)", rf"\g<1>{today}\g<2>", s)
    if new != s:
        sitemap.write_text(new, encoding="utf-8")


def main() -> int:
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    changed = []
    for lang, feed_url in FEEDS.items():
        rel = PAGES[lang]
        print(f"[{lang}] {feed_url}")
        xml = fetch(feed_url)
        items = parse_items(xml) if xml else []
        if not items:
            print(f"::warning::No usable posts from the {lang} Journal feed; {rel} left unchanged")
            continue
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        attach_images(items, text)
        new = apply_block(text, render_block(items, lang))
        if new == text:
            print(f"  {len(items)} posts, {rel} already up to date")
            continue
        path.write_text(new, encoding="utf-8")
        bump_lastmod(rel, today)
        changed.append(rel)
        print(f"  {len(items)} posts written to {rel}")

    if changed:
        # JSON-LD lists the same posts; regenerate it (and the CSP hash).
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate-structured-data.py")], check=True)
    print("Changed: " + (", ".join(changed) if changed else "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

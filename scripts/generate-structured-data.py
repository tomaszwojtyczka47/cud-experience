#!/usr/bin/env python3
"""
Structured-data (JSON-LD) generator for cudexperience.com.

The site is static HTML with no build step, so this is a small dev-time tool,
in the same spirit as scripts/check-site-integrity.py. It keeps one linked
schema.org graph per page (Organization, WebSite, Person, WebPage,
BreadcrumbList and, on the Hoi An pages, Event / TouristTrip /
TouristDestination / FAQPage) in sync between the English and Polish pages,
and recomputes the CSP sha256 hash of the inline JSON-LD block so the page's
Content-Security-Policy keeps matching.

What is derived from the page itself (so it cannot drift from what visitors
read): <title>, meta description, canonical URL, og:image(+alt), the Hoi An
room names / prices / descriptions, the FAQ questions and answers, and the
experiences list. What is configured below: entity identifiers, language
strings, breadcrumb labels and the offer validity window.

Usage:
    python3 scripts/generate-structured-data.py          # rewrite the pages
    python3 scripts/generate-structured-data.py --check  # exit 1 if any page is stale

Stdlib only. Run it after changing anything this file derives data from
(room prices, FAQ, titles, offer dates) and commit the result.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://cudexperience.com"

# --- Stable, language-neutral entity identifiers -----------------------------
ORG_ID = f"{BASE}/#organization"
SITE_ID = f"{BASE}/#website"
FOUNDER_ID = f"{BASE}/#founder"
LOGO_ID = f"{BASE}/#logo"
HOIAN_NS = f"{BASE}/experiences/hoi-an/"
EVENT_ID = f"{HOIAN_NS}#event"
TRIP_ID = f"{HOIAN_NS}#trip"
DEST_ID = f"{HOIAN_NS}#destination"

# Offer window for the C.U.D. Origins Founding Edition. Keep in sync with the
# "applications close 30 November 2026" sentence in the Investment section.
OFFER_VALID_FROM = "2026-09-04"
OFFER_VALID_THROUGH = "2026-11-30T23:59:59+01:00"

INSTAGRAM = "https://www.instagram.com/cudexperience/"

# Verified sameAs targets (Wikidata / Wikipedia / UNESCO pages checked 2026-10-01).
COUNTRIES = [
    ("Indonesia", ["https://www.wikidata.org/wiki/Q252", "https://en.wikipedia.org/wiki/Indonesia"]),
    ("Vietnam", ["https://www.wikidata.org/wiki/Q881", "https://en.wikipedia.org/wiki/Vietnam"]),
    ("Cambodia", ["https://www.wikidata.org/wiki/Q424", "https://en.wikipedia.org/wiki/Cambodia"]),
]
HOIAN_SAMEAS = [
    "https://www.wikidata.org/wiki/Q36160",
    "https://en.wikipedia.org/wiki/H%E1%BB%99i_An_(city)",
    "https://pl.wikipedia.org/wiki/H%E1%BB%99i_An",
]
HOIAN_OLD_TOWN_SAMEAS = "https://whc.unesco.org/en/list/948/"

# Type used for the site-wide entity. The Terms of Use state the site is not a
# travel agency / tour operator / booking platform, so "TravelAgency" is
# deliberately not used here. Change this one constant to switch.
ORG_TYPE = "Organization"

# --- Per-language strings ----------------------------------------------------
LANG = {
    "en": {
        "prefix": "",
        "org_desc": "C.U.D. Experience (short for \u201cCurated Human Experiences\u201d) is a small, independent slow-travel brand created and curated by Piotr Pawe\u0142 Kami\u0144ski. It designs and hosts small-group experiences in Asia (Vietnam, Indonesia, Cambodia), built around real conversations, local culture and unhurried days. Its first experience, C.U.D. Origins\u2122, takes place in Hoi An, Vietnam, in March 2027 for a maximum of nine guests.",
        "slogan": "Travel slower. Feel deeper. Return to yourself.",
        "knows": ["slow travel", "experiences in Asia", "curated journeys"],
        "root_crumb": "C.U.D. Experience",
        "founder_title": "Founder & Curator",
        "founder_desc": "Founder and curator of C.U.D. Experience, who designs and personally hosts its small-group experiences.",
        "event_desc": "Eleven days of slow travel in Hoi An, Vietnam — local culture, quiet mornings and real connection.",
        "trip_desc": "A private human experience for 9 people: 10 nights in a private riverside sanctuary in Hoi An, Vietnam, 20–30 March 2027.",
        "trip_types": ["Solo travellers", "Couples"],
        "dest_desc": "Hoi An, Vietnam: the setting for C.U.D. Origins™, a private riverside sanctuary with tropical gardens, close to Hoi An Old Town.",
        "old_town": "Hoi An Old Town",
        "per_couple": "price per couple",
    },
    "pl": {
        "prefix": "pl/",
        "org_desc": "C.U.D. Experience („Curated Human Experiences”) to mała, niezależna marka slow travel, stworzona i prowadzona przez Piotra Pawła Kamińskiego. Projektuje i prowadzi kameralne doświadczenia w Azji (Wietnam, Indonezja, Kambodża), oparte na prawdziwych rozmowach, lokalnej kulturze i dniach bez pośpiechu. Jej pierwsze doświadczenie, C.U.D. Origins™, odbędzie się w Hoi An w Wietnamie w marcu 2027 dla maksymalnie dziewięciu gości.",
        "slogan": "Podróżuj wolniej. Czuj głębiej. Wróć do siebie.",
        "knows": ["slow travel", "doświadczenia w Azji", "podróże szyte na miarę"],
        "root_crumb": "C.U.D. Experience",
        "founder_title": "Założyciel i Kurator",
        "founder_desc": "Założyciel i kurator C.U.D. Experience, który projektuje i osobiście prowadzi jego kameralne doświadczenia.",
        "event_desc": "Jedenaście dni slow travel w Hoi An w Wietnamie — lokalna kultura, ciche poranki i prawdziwe relacje.",
        "trip_desc": "Prywatne, ludzkie doświadczenie dla 9 osób: 10 nocy w prywatnej oazie nad rzeką w Hoi An w Wietnamie, 20–30 marca 2027.",
        "trip_types": ["Osoby podróżujące solo", "Pary"],
        "dest_desc": "Hoi An w Wietnamie: miejsce C.U.D. Origins™, prywatnej oazy nad rzeką wśród tropikalnych ogrodów, blisko Starego Miasta Hoi An.",
        "old_town": "Stare Miasto Hoi An",
        "per_couple": "cena za parę",
    },
}

# --- Page registry -----------------------------------------------------------
# path (relative to the language root), schema type, breadcrumb trail
# [(path, {lang: label})] below the home page, and whether the page carries
# the Hoi An experience entities.
HOIAN_CRUMB = ("experiences/hoi-an/", {"en": "C.U.D. Hoi An Experience", "pl": "C.U.D. Hoi An Experience"})
EXP_CRUMB = ("experiences/", {"en": "Experiences", "pl": "Experiences"})
PAGES = [
    {"path": "", "type": "WebPage", "crumbs": [], "about_org": True},
    {"path": "about/", "type": "AboutPage", "crumbs": [("about/", {"en": "About C.U.D.", "pl": "O C.U.D."})], "about_org": True},
    {"path": "philosophy/", "type": "WebPage", "crumbs": [("philosophy/", {"en": "Philosophy", "pl": "Filozofia"})], "about_org": True},
    {"path": "journal/", "type": "CollectionPage", "crumbs": [("journal/", {"en": "Journal", "pl": "Journal"})], "journal_feed": True},
    {"path": "contact/", "type": "ContactPage", "crumbs": [("contact/", {"en": "Contact", "pl": "Kontakt"})], "about_org": True},
    {"path": "privacy/", "type": "WebPage", "crumbs": [("privacy/", {"en": "Privacy Policy", "pl": "Polityka Prywatności"})]},
    {"path": "terms/", "type": "WebPage", "crumbs": [("terms/", {"en": "Terms of Use", "pl": "Regulamin"})]},
    {"path": "experiences/", "type": "CollectionPage", "crumbs": [EXP_CRUMB], "experience_list": True},
    {"path": "experiences/hoi-an/", "type": "WebPage", "crumbs": [EXP_CRUMB, HOIAN_CRUMB], "hoian": True},
    {"path": "experiences/hoi-an/apply/", "type": "WebPage", "crumbs": [EXP_CRUMB, HOIAN_CRUMB, ("experiences/hoi-an/apply/", {"en": "Apply", "pl": "Zgłoszenie"})]},
]


# --- HTML extraction helpers -------------------------------------------------
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>\n?', re.S)
CSP_RE = re.compile(r'(<meta http-equiv="Content-Security-Policy" content=")([^"]*)(")', re.I)
SHA_RE = re.compile(r"'sha256-([A-Za-z0-9+/=]+)'")


def clean(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", fragment)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def meta(text: str, attr: str, name: str) -> str | None:
    m = re.search(r'<meta %s="%s" content="([^"]*)"' % (attr, re.escape(name)), text)
    return html.unescape(m.group(1)) if m else None


def sha256_b64(body: str) -> str:
    return base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")


def page_url(lang: str, path: str) -> str:
    return f"{BASE}/{LANG[lang]['prefix']}{path}"


def rooms(text: str) -> list[dict]:
    pat = re.compile(
        r'<h3>([^<]+)</h3>\s*<p class="cud-space-tag">.*?</p>\s*<p class="cud-space-feat">(.*?)</p>\s*'
        r'<p class="cud-space-meta">(.*?)</p>\s*<p class="cud-space-price">(.*?)</p>\s*</button>\s*'
        r'<p class="cud-space-loc" hidden>(.*?)</p>', re.S)
    out = []
    for name, feat, meta_line, price_html, loc in pat.findall(text):
        unit = re.search(r'<span class="cud-space-unit">(.*?)</span>', price_html)
        price_txt = clean(re.sub(r'<span class="cud-space-unit">.*?</span>', "", price_html))
        digits = re.sub(r"\D", "", price_txt)
        currency = re.search(r"[A-Z]{3}", price_txt)
        out.append({
            "name": clean(name), "feat": clean(feat), "meta": clean(meta_line), "loc": clean(loc),
            "price": digits, "currency": currency.group(0) if currency else "PLN",
            "couple": bool(unit),
        })
    return out


def faq_items(text: str) -> list[tuple[str, str]]:
    pat = re.compile(r'<li class="cud-faq-item"><details><summary>(.*?)</summary><p>(.*?)</p></details></li>', re.S)
    return [(clean(q), clean(a)) for q, a in pat.findall(text)]


def experience_items(text: str, lang: str) -> list[tuple[str, str]]:
    pat = re.compile(r'<a class="cud-ev[^"]*" href="([^"]+)">.*?<h2>(.*?)</h2>', re.S)
    items = []
    for href, name in pat.findall(text):
        assert not href.startswith("http"), href
        items.append((page_url(lang, "experiences/" + href), clean(name)))
    return items


def journal_posts(text: str) -> list[dict]:
    """Posts pre-rendered by scripts/sync-journal.py between the journal-feed markers.
    Besides title/date/excerpt, each card carries the blog's own author and image
    (data-* attributes); a post without them simply has no such field."""
    m = re.search(r"<!-- journal-feed:start.*?-->(.*?)<!-- journal-feed:end -->", text, re.S)
    if not m:
        return []
    body_re = re.compile(
        r'<span class="cud-jrl-date">(?:<time datetime="([^"]*)">)?.*?</span>'
        r'<span class="cud-jrl-h">(.*?)</span><span class="cud-jrl-ex">(.*?)</span>', re.S)
    posts = []
    for attrs, inner in re.findall(r'<a class="cud-jrl-card"([^>]*)>(.*?)</a>', m.group(1), re.S):
        a = {k: html.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', attrs)}
        b = body_re.search(inner)
        if not a.get("href") or not b:
            continue
        image = None
        if a.get("data-image"):
            image = {"url": a["data-image"]}
            for dim in ("width", "height"):
                if a.get(f"data-image-{dim}", "").isdigit():
                    image[dim] = int(a[f"data-image-{dim}"])
        posts.append({
            "url": a["href"], "date": b.group(1), "title": clean(b.group(2)), "excerpt": clean(b.group(3)),
            "author": a.get("data-author"), "author_url": a.get("data-author-url"), "image": image,
        })
    return posts


# --- Graph builders ----------------------------------------------------------
def org_node(lang: str) -> dict:
    s = LANG[lang]
    return {
        "@type": ORG_TYPE,
        "@id": ORG_ID,
        "name": "C.U.D. Experience",
        "alternateName": ["Curated Human Experiences", "CUD Experience"],
        "url": f"{BASE}/",
        "logo": {"@type": "ImageObject", "@id": LOGO_ID, "url": f"{BASE}/android-chrome-512x512.png",
                 "width": 512, "height": 512, "caption": "C.U.D. Experience"},
        "image": f"{BASE}/assets/images/01-hero.jpg",
        "email": "contact@cudexperience.com",
        "contactPoint": {"@type": "ContactPoint", "contactType": "customer support",
                         "email": "contact@cudexperience.com", "availableLanguage": ["English", "Polish"]},
        "sameAs": [INSTAGRAM],
        "founder": {"@id": FOUNDER_ID},
        "address": {"@type": "PostalAddress", "addressCountry": "PL"},
        "slogan": s["slogan"],
        "description": s["org_desc"],
        "areaServed": [{"@type": "Country", "name": n, "sameAs": same} for n, same in COUNTRIES],
        "knowsAbout": s["knows"],
    }


def website_node() -> dict:
    return {"@type": "WebSite", "@id": SITE_ID, "url": f"{BASE}/", "name": "C.U.D. Experience",
            "publisher": {"@id": ORG_ID}, "inLanguage": ["en", "pl"]}


def founder_node(lang: str) -> dict:
    return {"@type": "Person", "@id": FOUNDER_ID, "name": "Piotr Paweł Kamiński",
            "jobTitle": LANG[lang]["founder_title"], "description": LANG[lang]["founder_desc"],
            "url": page_url(lang, "about/") + "#founder", "worksFor": {"@id": ORG_ID}}


def hoian_nodes(text: str, lang: str, url: str) -> list[dict]:
    s = LANG[lang]
    apply_url = page_url(lang, "experiences/hoi-an/apply/")
    offers = []
    for r in rooms(text):
        desc = f"{r['feat']}. {r['loc']}. {r['meta']}"
        desc += f", {s['per_couple']}." if r["couple"] else "."
        offers.append({
            "@type": "Offer", "validFrom": OFFER_VALID_FROM, "validThrough": OFFER_VALID_THROUGH,
            "name": r["name"], "description": desc, "price": r["price"], "priceCurrency": r["currency"],
            "availability": "https://schema.org/InStock", "url": apply_url,
        })
    org_ref = {"@type": "Organization", "@id": ORG_ID, "name": "C.U.D. Experience", "url": f"{BASE}/",
               "sameAs": [INSTAGRAM]}
    event = {
        "@type": "Event", "@id": EVENT_ID,
        "name": "C.U.D. Hoi An Experience",
        "alternateName": ["C.U.D. Origins™", "C.U.D. Origins™ Founding Edition"],
        "description": s["event_desc"],
        "startDate": "2027-03-20", "endDate": "2027-03-30",
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "image": [f"{BASE}/assets/images/hoian-hero.jpg", f"{BASE}/assets/images/hoian-closing.jpg"],
        "url": url,
        "location": {
            "@type": "Place", "@id": DEST_ID, "name": "Hoi An",
            "address": {"@type": "PostalAddress", "addressLocality": "Hoi An", "addressRegion": "Da Nang",
                        "addressCountry": "VN"},
            "geo": {"@type": "GeoCoordinates", "latitude": 15.8801, "longitude": 108.338},
        },
        "organizer": dict(org_ref, logo=f"{BASE}/android-chrome-192x192.png"),
        "performer": org_ref,
        "maximumAttendeeCapacity": 9,
        "isAccessibleForFree": False,
        "about": {"@id": TRIP_ID},
        "offers": offers,
        "inLanguage": lang,
    }
    trip = {
        "@type": "TouristTrip", "@id": TRIP_ID, "name": "C.U.D. Hoi An Experience",
        "alternateName": ["C.U.D. Origins™", "C.U.D. Origins™ Founding Edition"],
        "description": s["trip_desc"], "url": url,
        "touristType": s["trip_types"],
        "itinerary": {"@id": DEST_ID},
        "provider": {"@id": ORG_ID},
    }
    dest = {
        "@type": "TouristDestination", "@id": DEST_ID, "name": "Hoi An",
        "description": s["dest_desc"],
        "address": {"@type": "PostalAddress", "addressLocality": "Hoi An", "addressRegion": "Da Nang",
                    "addressCountry": "VN"},
        "geo": {"@type": "GeoCoordinates", "latitude": 15.8801, "longitude": 108.338},
        "containedInPlace": {"@type": "Country", "name": "Vietnam", "sameAs": COUNTRIES[1][1]},
        "sameAs": HOIAN_SAMEAS,
        "includesAttraction": {"@type": "TouristAttraction", "name": s["old_town"],
                               "sameAs": HOIAN_OLD_TOWN_SAMEAS},
    }
    nodes = [event, trip, dest]
    faq = faq_items(text)
    if faq:
        nodes.append({
            "@type": "FAQPage", "@id": f"{url}#faq",
            "isPartOf": {"@id": f"{url}#webpage"}, "inLanguage": lang,
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                           for q, a in faq],
        })
    return nodes


def build_graph(page: dict, lang: str, text: str) -> list[dict]:
    path = page["path"]
    url = page_url(lang, path)
    other = "pl" if lang == "en" else "en"
    other_url = page_url(other, path)
    title = clean(re.search(r"<title>(.*?)</title>", text, re.S).group(1))
    desc = meta(text, "name", "description")

    web = {"@type": page["type"], "@id": f"{url}#webpage", "url": url, "name": title, "isPartOf": {"@id": SITE_ID},
           "inLanguage": lang}
    if desc:
        web["description"] = desc
    web["workTranslation" if lang == "en" else "translationOfWork"] = {"@id": f"{other_url}#webpage"}

    graph = [org_node(lang), website_node(), founder_node(lang), web]

    if page.get("about_org"):
        web["about"] = {"@id": ORG_ID}
    if page["crumbs"]:
        items = [{"@type": "ListItem", "position": 1, "name": LANG[lang]["root_crumb"], "item": page_url(lang, "")}]
        for i, (p, names) in enumerate(page["crumbs"], start=2):
            items.append({"@type": "ListItem", "position": i, "name": names[lang], "item": page_url(lang, p)})
        graph.append({"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb", "itemListElement": items})
        web["breadcrumb"] = {"@id": f"{url}#breadcrumb"}

    og_image = meta(text, "property", "og:image")
    if og_image:
        img = {"@type": "ImageObject", "@id": f"{url}#primaryimage", "url": og_image, "contentUrl": og_image}
        w, h = meta(text, "property", "og:image:width"), meta(text, "property", "og:image:height")
        if w and h:
            img["width"], img["height"] = int(w), int(h)
        alt = meta(text, "property", "og:image:alt")
        if alt:
            img["caption"] = alt
        graph.append(img)
        web["primaryImageOfPage"] = {"@id": f"{url}#primaryimage"}

    if page.get("experience_list"):
        items = experience_items(text, lang)
        web["mainEntity"] = {
            "@type": "ItemList", "@id": f"{url}#list",
            "itemListElement": [{"@type": "ListItem", "position": i, "url": u, "name": n}
                                for i, (u, n) in enumerate(items, start=1)],
        }
    if page.get("journal_feed"):
        posts = journal_posts(text)
        if posts:
            items = []
            for i, p in enumerate(posts, start=1):
                post = {"@type": "BlogPosting", "headline": p["title"], "url": p["url"], "inLanguage": lang}
                if p["date"]:
                    post["datePublished"] = p["date"]
                if p["excerpt"]:
                    post["description"] = p["excerpt"]
                if p["author"]:
                    post["author"] = {"@type": "Person", "name": p["author"]}
                    if p["author_url"]:
                        post["author"]["url"] = p["author_url"]
                if p["image"]:
                    post["image"] = {"@type": "ImageObject", **p["image"]}
                items.append({"@type": "ListItem", "position": i, "item": post})
            web["mainEntity"] = {"@type": "ItemList", "@id": f"{url}#posts", "itemListElement": items}
    if page.get("hoian"):
        web["mainEntity"] = {"@id": EVENT_ID}
        web["about"] = [{"@id": TRIP_ID}, {"@id": DEST_ID}]
        graph.extend(hoian_nodes(text, lang, url))
    return graph


# --- Page rewriting ----------------------------------------------------------
def render_block(graph: list[dict]) -> str:
    doc = {"@context": "https://schema.org", "@graph": graph}
    body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return "\n" + body + "\n"


def rewrite(text: str, graph: list[dict]) -> str:
    body = render_block(graph)
    old_bodies = [m.group(1) for m in LD_RE.finditer(text)]
    new_hash = sha256_b64(body)

    seen = []

    def swap(m: re.Match) -> str:
        if seen:
            return ""
        seen.append(1)
        return f'<script type="application/ld+json">{body}</script>\n'

    if old_bodies:
        text = LD_RE.sub(swap, text)
    else:
        raise SystemExit("page has no existing JSON-LD block to replace; add one first")

    def fix_csp(m: re.Match) -> str:
        csp = m.group(2)
        old_hashes = [sha256_b64(b) for b in old_bodies]
        # replace the first old hash in place, drop any further old ones
        replaced = False
        for h in old_hashes:
            token = f"'sha256-{h}'"
            if h == new_hash:
                replaced = True
                continue
            if token in csp:
                if not replaced:
                    csp = csp.replace(token, f"'sha256-{new_hash}'", 1)
                    replaced = True
                else:
                    csp = csp.replace(" " + token, "", 1)
        if f"'sha256-{new_hash}'" not in csp:
            # no old hash to replace: append after the last hash in script-src
            hashes = list(SHA_RE.finditer(csp))
            at = hashes[-1].end() if hashes else csp.index("script-src") + len("script-src")
            csp = csp[:at] + f" 'sha256-{new_hash}'" + csp[at:]
        return m.group(1) + csp + m.group(3)

    return CSP_RE.sub(fix_csp, text, count=1)


def main() -> int:
    check = "--check" in sys.argv[1:]
    stale = []
    for page in PAGES:
        for lang in ("en", "pl"):
            rel = f"{LANG[lang]['prefix']}{page['path']}index.html"
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            new = rewrite(text, build_graph(page, lang, text))
            if new != text:
                stale.append(rel)
                if not check:
                    path.write_text(new, encoding="utf-8")
    if check:
        if stale:
            print("Structured data is out of date for:\n  " + "\n  ".join(stale))
            print("Run: python3 scripts/generate-structured-data.py")
            return 1
        print("OK: structured data is up to date")
        return 0
    print(f"Updated {len(stale)} page(s)" + (":\n  " + "\n  ".join(stale) if stale else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

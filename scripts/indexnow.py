#!/usr/bin/env python3
"""
IndexNow ping for cudexperience.com.

IndexNow (https://www.indexnow.org) lets a site tell Bing, Yandex, Naver and
Seznam which URLs changed, so they re-crawl them sooner. Bing also feeds
Microsoft Copilot. Google does not support IndexNow, so it has no effect there.

The protocol needs a key file at the site root whose name and content are the
key (the <32 hex chars>.txt file in this repository). The key is public by
design: it only proves that this host's owner sent the request.

Usage:
    python3 scripts/indexnow.py --changed-between BASE HEAD   # pages touched in that git range
    python3 scripts/indexnow.py --all                         # every page listed in sitemap.xml
    add --dry-run to print the URLs without sending anything

Only pages that are listed in sitemap.xml are ever sent, so noindex pages (404,
thank-you pages, redirect stubs) are skipped. Run by .github/workflows/indexnow.yml
after each GitHub Pages deployment. Stdlib only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "cudexperience.com"
ENDPOINT = "https://api.indexnow.org/IndexNow"
KEY_FILE_RE = re.compile(r"^[0-9a-f]{32}\.txt$")


def find_key() -> str:
    keys = [p for p in ROOT.glob("*.txt") if KEY_FILE_RE.match(p.name)]
    if len(keys) != 1:
        raise SystemExit(f"expected exactly one <32 hex chars>.txt key file in the repository root, found {len(keys)}")
    key = keys[0].read_text(encoding="utf-8").strip()
    if key != keys[0].stem:
        raise SystemExit(f"{keys[0].name}: the file content must be the key itself ({keys[0].stem})")
    return key


def sitemap_urls() -> list[str]:
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tree = ET.parse(ROOT / "sitemap.xml")
    return [el.text.strip() for el in tree.getroot().findall("sm:url/sm:loc", ns) if el.text]


def url_for(rel_path: str) -> str | None:
    """index.html -> https://host/, a/b/index.html -> https://host/a/b/, anything else -> None."""
    if rel_path == "index.html":
        return f"https://{HOST}/"
    if rel_path.endswith("/index.html"):
        return f"https://{HOST}/{rel_path[: -len('index.html')]}"
    return None


def changed_urls(base: str, head: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", base, head], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout.split()
    listed = set(sitemap_urls())
    urls = []
    for rel in out:
        url = url_for(rel)
        if url and url in listed and url not in urls:
            urls.append(url)
    return urls


def send(key: str, urls: list[str]) -> None:
    body = json.dumps({"host": HOST, "key": key, "keyLocation": f"https://{HOST}/{key}.txt", "urlList": urls}).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": "cudexperience-indexnow/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"IndexNow answered HTTP {resp.status} for {len(urls)} URL(s)")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"IndexNow rejected the request: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    if "--all" in argv:
        urls = sitemap_urls()
    elif "--changed-between" in argv:
        i = argv.index("--changed-between")
        if len(argv) < i + 3:
            raise SystemExit("--changed-between needs BASE and HEAD")
        urls = changed_urls(argv[i + 1], argv[i + 2])
    else:
        raise SystemExit(__doc__)
    key = find_key()
    if not urls:
        print("No indexable page changed, nothing to send.")
        return 0
    print("URLs:\n  " + "\n  ".join(urls))
    if dry:
        print(f"Dry run: would send {len(urls)} URL(s) with key {key[:6]}... to {ENDPOINT}")
        return 0
    send(key, urls)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

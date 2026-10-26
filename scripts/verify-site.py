#!/usr/bin/env python3
"""
Check that a server serves cudexperience.com exactly like the repository says it should.

The reference is the folder built by scripts/build-site.py (default cud-site/ in the temp folder), so run that
first. Files inside it are what the server must return.

Two ways to run it:

    python3 scripts/verify-site.py
        Asks the live site (through Cloudflare) and checks status codes, content types,
        cache headers, the /about -> /about/ redirect, the 404 page and the three
        Cloudflare Worker endpoints under /api/. Uses a small
        sample of files and waits between requests so Cloudflare's rate limit
        (40 requests / 10 s per IP) is never hit.

    python3 scripts/verify-site.py --origin-host h69.seohost.pl
        Talks straight to the seohost server (Cloudflare is not involved, nothing is
        cached anywhere) with Host: cudexperience.com and TLS verification off, and
        compares every deployed file byte for byte (SHA-256) with the built folder.
        Use it before the DNS switch, and again after every deployment.

Exit code 0 = everything passed, 1 = at least one check failed. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "cudexperience.com"
DEFAULT_SITE = Path(tempfile.gettempdir()) / "cud-site"

MEDIA_TYPES = {
    ".html": {"text/html"},
    ".css": {"text/css"},
    ".js": {"application/javascript", "text/javascript", "application/x-javascript"},
    ".txt": {"text/plain"},
    ".xml": {"application/xml", "text/xml"},
    ".webmanifest": {"application/manifest+json"},
    ".svg": {"image/svg+xml"},
    ".ico": {"image/vnd.microsoft.icon", "image/x-icon"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".woff2": {"font/woff2"},
}
TEXT_EXTENSIONS = {".html", ".css", ".js", ".txt"}
SAMPLE = (
    "robots.txt", "llms.txt", "sitemap.xml", "site.webmanifest", "favicon.ico", "favicon.svg",
    "apple-touch-icon.png", ".well-known/security.txt", "assets/css/style.css", "assets/js/site.js",
    "assets/fonts/jost-latin.woff2",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Fetcher:
    def __init__(self, origin_host: str | None, delay: float) -> None:
        self.origin_host = origin_host
        self.delay = delay
        context = ssl._create_unverified_context() if origin_host else ssl.create_default_context()
        self.opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=context))

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        time.sleep(self.delay)
        netloc = self.origin_host or HOST
        request = urllib.request.Request(f"https://{netloc}{path}", headers={"User-Agent": "cud-verify-site/1", "Accept-Encoding": "identity"})
        if self.origin_host:
            request.add_header("Host", HOST)
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
        except urllib.error.HTTPError as error:
            return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


    def post_json(self, path: str, payload: str) -> tuple[int, dict[str, str], bytes]:
        time.sleep(self.delay)
        request = urllib.request.Request(
            f"https://{HOST}{path}", data=payload.encode("utf-8"), method="POST",
            headers={"User-Agent": "cud-verify-site/1", "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
        except urllib.error.HTTPError as error:
            return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


class Report:
    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0
        self.passed = 0

    def ok(self) -> None:
        self.passed += 1

    def fail(self, message: str) -> None:
        self.failures += 1
        print(f"FAIL  {message}")

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f"WARN  {message}")


def served_files(site: Path) -> list[str]:
    names = [path.relative_to(site).as_posix() for path in site.rglob("*") if path.is_file()]
    return sorted(name for name in names if name != ".htaccess")


def url_path(rel: str) -> str:
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def check_file(fetcher: Fetcher, report: Report, site: Path, rel: str, compare_bytes: bool) -> None:
    path = url_path(rel)
    status, headers, body = fetcher.get(path)
    if status != 200 and not (rel == "404.html" and status == 404):
        report.fail(f"{path}: HTTP {status}, expected 200")
        return
    extension = Path(rel).suffix.lower()
    content_type = headers.get("content-type", "")
    media_type = content_type.split(";")[0].strip().lower()
    expected = MEDIA_TYPES.get(extension)
    if expected and media_type not in expected:
        report.fail(f"{path}: content-type '{content_type}', expected one of {sorted(expected)}")
        return
    if extension in TEXT_EXTENSIONS and "utf-8" not in content_type.lower():
        report.warn(f"{path}: content-type '{content_type}' has no charset=utf-8")
    if "max-age" not in headers.get("cache-control", ""):
        report.warn(f"{path}: no Cache-Control max-age header, browsers will guess how long to keep it")
    if compare_bytes:
        if hashlib.sha256(body).hexdigest() != hashlib.sha256((site / rel).read_bytes()).hexdigest():
            report.fail(f"{path}: the bytes on the server differ from {rel} in the built folder")
            return
    report.ok()


def check_behaviour(fetcher: Fetcher, report: Report) -> None:
    for page in ("/about", "/pl/about", "/experiences/hoi-an"):
        status, headers, _ = fetcher.get(page)
        location = headers.get("location", "")
        if status == 301 and location.rstrip("/").endswith(page) and location.endswith("/"):
            report.ok()
        else:
            report.fail(f"{page}: expected 301 to {page}/, got HTTP {status} Location '{location}'")
    for page in ("/privacy", "/terms"):
        status, headers, body = fetcher.get(page)
        if status == 301 and headers.get("location", "").endswith(page + "/"):
            report.ok()
        elif status == 200 and f"url={page}/".encode() in body:
            report.ok()
        else:
            report.fail(f"{page}: expected 301 to {page}/ (seohost) or the redirect stub (GitHub Pages), got HTTP {status}")
    status, _, body = fetcher.get("/this-page-does-not-exist-9f3a")
    if status == 404 and b"Page Not Found" in body:
        report.ok()
    else:
        report.fail(f"unknown URL: expected HTTP 404 with the C.U.D. 404 page, got HTTP {status}")
    status, _, body = fetcher.get("/assets/this-file-does-not-exist.css")
    if status == 404:
        report.ok()
    else:
        report.fail(f"missing asset: expected HTTP 404, got HTTP {status}")
    status, headers, _ = fetcher.get("/.git/config")
    if status in (403, 404):
        report.ok()
    else:
        report.fail(f"/.git/config: expected 403 or 404, got HTTP {status}")
    status, headers, _ = fetcher.get("/scripts/check-site-integrity.py")
    if status == 404:
        report.ok()
    else:
        report.warn(f"/scripts/check-site-integrity.py: HTTP {status}; maintainer scripts should not be public")


def check_workers(fetcher: Fetcher, report: Report) -> None:
    for lang in ("en", "pl"):
        status, headers, body = fetcher.get(f"/api/journal?lang={lang}")
        if status == 200 and "json" in headers.get("content-type", "") and body.lstrip().startswith((b"{", b"[")):
            report.ok()
        else:
            report.fail(f"/api/journal?lang={lang}: expected 200 JSON from the Cloudflare Worker, got HTTP {status} {headers.get('content-type', '')}")
    status, headers, body = fetcher.post_json("/api/apply", "{}")
    if status == 400 and b"missing_turnstile_token" in body:
        report.ok()
    else:
        report.fail(f"POST /api/apply with an empty body: expected 400 missing_turnstile_token from the Worker, got HTTP {status}")


def check_sitemap(fetcher: Fetcher, report: Report, site: Path) -> None:
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [el.text.strip() for el in ET.parse(site / "sitemap.xml").getroot().findall("sm:url/sm:loc", namespace) if el.text]
    for location in locations:
        path = "/" + location.split("://", 1)[1].split("/", 1)[1]
        status, _, _ = fetcher.get(path)
        if status == 200:
            report.ok()
        else:
            report.fail(f"sitemap URL {path}: HTTP {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origin-host", help="talk straight to this server (for example h69.seohost.pl) instead of the live site")
    parser.add_argument("--site-dir", default=str(DEFAULT_SITE), help=f"folder built by scripts/build-site.py (default: {DEFAULT_SITE})")
    parser.add_argument("--delay", type=float, help="seconds between requests (default 0.05 for the origin, 0.4 for the live site)")
    args = parser.parse_args()

    site = Path(args.site_dir).resolve()
    if not (site / "index.html").is_file():
        raise SystemExit(f"{site} has no index.html: run python3 scripts/build-site.py first")
    delay = args.delay if args.delay is not None else (0.05 if args.origin_host else 0.4)
    fetcher = Fetcher(args.origin_host, delay)
    report = Report()

    files = served_files(site)
    to_check = files if args.origin_host else [name for name in files if name in SAMPLE or name == "index.html" or name == "404.html"]
    target = args.origin_host or HOST
    print(f"Checking {len(to_check)} files, the sitemap and server behaviour on {target} ...")
    for rel in to_check:
        check_file(fetcher, report, site, rel, compare_bytes=bool(args.origin_host))
    check_sitemap(fetcher, report, site)
    check_behaviour(fetcher, report)
    if not args.origin_host:
        check_workers(fetcher, report)

    print(f"\n{report.passed} checks passed, {report.failures} failed, {report.warnings} warning(s)")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())

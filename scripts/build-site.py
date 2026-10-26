#!/usr/bin/env python3
"""
Builds the folder that is uploaded to the seohost server (default: cud-site/ in the
system temp folder, outside the repository so the other checkers do not scan it).

The site has no build step. This script only decides what visitors may get: every
file tracked by git except the maintainer files (.github/, scripts/, worker/,
deploy/, CNAME, .nojekyll, .gitignore), plus deploy/htaccess as .htaccess.

Used by .github/workflows/deploy-seohost.yml and by scripts/verify-site.py, which
compares the server with this folder. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = "cud-site"
DEFAULT_OUT = Path(tempfile.gettempdir()) / FOLDER
EXCLUDED = re.compile(r"^(\.github/|scripts/|worker/|deploy/|\.gitignore$|\.nojekyll$|CNAME$)")


def deployed_files() -> list[str]:
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    names = [name for name in listing.decode("utf-8").split("\0") if name and not EXCLUDED.match(name)]
    return sorted(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"output folder, emptied first (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        if out.name != FOLDER:
            raise SystemExit(f"refusing to empty {out}: it is not empty and is not a folder named {FOLDER}")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    names = deployed_files()
    for name in names:
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(ROOT / "deploy" / "htaccess", out / ".htaccess")

    size = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    print(f"{out}: {len(names)} files + .htaccess, {size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()

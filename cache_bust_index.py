#!/usr/bin/env python3
"""After pygbag --build, patch index.html so browsers fetch fresh APK/tar.gz (not a cached copy)."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "build" / "web" / "index.html"


def main():
    if not INDEX.is_file():
        print("Run from project root after: pygbag --build .", file=sys.stderr)
        sys.exit(1)
    v = str(int(time.time()))
    text = INDEX.read_text(encoding="utf-8")
    # fopen("testing.tar.gz" — must match template exactly
    new = text.replace('"testing.tar.gz"', f'"testing.tar.gz?v={v}"')
    new = new.replace('"testing.apk"', f'"testing.apk?v={v}"')
    if new == text:
        print("No archive URLs patched — template may have changed.", file=sys.stderr)
        sys.exit(1)
    INDEX.write_text(new, encoding="utf-8")
    print(f"Patched {INDEX.name} cache bust v={v}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate/check the itemized inventory of maintained OS implementation inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "mseries/rust/source-inventory.json"
DIRECTORIES = (
    "bin",
    "transform",
    "repos",
    "mkosi.images",
    "mkosi.conf.d",
    ".github/workflows",
    "mseries",
)
ROOT_FILES = ("Justfile", "mkosi.conf", "packages.arm64")
EXTENSIONS = {
    ".c", ".cc", ".conf", ".cpp", ".desktop", ".diff", ".h", ".js",
    ".json", ".lock", ".meson", ".mjs", ".patch", ".policy", ".py",
    ".qml", ".rules", ".rs", ".service", ".sh", ".timer", ".toml",
    ".vala", ".xml",
}
EXCLUDED_PARTS = {".git", "__pycache__", "target", "build", ".pytest_cache"}
LANGUAGES = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".h": "c-header",
    ".js": "javascript", ".mjs": "javascript", ".py": "python",
    ".rs": "rust", ".sh": "shell", ".vala": "vala", ".meson": "meson",
}


def role(path: Path) -> str:
    name = path.name.lower()
    if path.suffix in {".patch", ".diff"}:
        return "upstream-patch"
    if name.startswith(("test_", "test-")) or "/tests/" in path.as_posix():
        return "verification"
    if path.suffix in {".conf", ".desktop", ".json", ".lock", ".policy", ".rules", ".service", ".timer", ".toml", ".xml"}:
        return "configuration-or-data"
    return "implementation"


def source_paths() -> list[Path]:
    found: set[Path] = set()
    for directory in DIRECTORIES:
        base = ROOT / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.resolve() == OUTPUT.resolve() or any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
                continue
            if path.suffix.lower() in EXTENSIONS or path.name in {"Justfile", "packages.arm64"}:
                found.add(path.relative_to(ROOT))
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            found.add(path.relative_to(ROOT))
    return sorted(found, key=lambda path: path.as_posix())


def render() -> str:
    items = []
    for path in source_paths():
        text = path.as_posix()
        local = (
            text.startswith(("bin/", "transform/", "repos/", "mkosi.conf.d/", ".github/workflows/", "mseries/"))
            or text in ROOT_FILES
            or text.startswith("mkosi.images/apple-silicon/")
        )
        items.append({
            "id": text,
            "path": text,
            "ownership": "mseries-maintained" if local else "elementary-os-upstream",
            "language": LANGUAGES.get(path.suffix.lower(), "data"),
            "role": role(path),
            "rust_status": "not-assessed" if local else "retain-upstream",
        })
    document = {
        "schema": 1,
        "generated_by": "mseries/rust/inventory.py",
        "scope": list(DIRECTORIES) + list(ROOT_FILES),
        "item_count": len(items),
        "items": items,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed inventory is stale")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != expected:
            print("Rust source inventory is stale; run python3 mseries/rust/inventory.py", file=sys.stderr)
            return 1
        print(f"Rust source inventory is current ({len(source_paths())} items)")
        return 0
    OUTPUT.write_text(expected)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(source_paths())} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

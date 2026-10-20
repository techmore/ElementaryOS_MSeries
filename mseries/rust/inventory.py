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
RUST_CANDIDATE_PREFIXES = (
    "mseries/rust/mseries-power/",
    "mseries/rust/wifi-resume/",
    "mseries/rust/netusage/",
    "mseries/rust/panel-provenance/",
    "mseries/rust/keyboard-backlight/",
)
RUST_FUNCTIONAL_PREFIXES = (
    "mseries/rust/netusage/",
    "mseries/rust/brightness-bridge/",
)
PROJECT_PREFIX_OVERRIDES = {
    "mseries/rust/mseries-power/": "mseries/power",
    "mseries/rust/wifi-resume/": "mseries/wifi-resume",
    "mseries/rust/netusage/": "mseries/netspeed/netusage",
    "mseries/rust/panel-provenance/": "mseries/panel",
    "mseries/rust/keyboard-backlight/": "mseries/keyboard-backlight",
    "mseries/rust/brightness-bridge/": "mseries/brightness",
}
PROJECT_PATH_OVERRIDES = {
    "mkosi.images/liveiso/mkosi.conf.d/arch.arm64.conf": "mseries/apple-silicon-image",
    "mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf": "mseries/apple-silicon-image",
    "mseries/install-keyboard-backlight.sh": "mseries/keyboard-backlight",
    "mseries/install-power.sh": "mseries/power",
    "mseries/test-power-cap.py": "mseries/power",
    "mseries/test-power-install.py": "mseries/power",
    "mseries/test-wifi-resume.py": "mseries/wifi-resume",
    "mseries/install-netusage-policy.sh": "mseries/netspeed/netusage",
    "mseries/panel-factory-pins.json": "mseries/panel",
    "mseries/install-sound-indicator-fix.sh": "mseries/panel",
    "mseries/install-keyboard-indicator-fix.sh": "mseries/panel",
    "mseries/install-brightness-bridge.sh": "mseries/brightness",
}
EXCLUDED_PARTS = {".git", "__pycache__", "target", "build", ".pytest_cache"}
LANGUAGES = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".h": "c-header",
    ".js": "javascript", ".mjs": "javascript", ".py": "python",
    ".rs": "rust", ".sh": "shell", ".vala": "vala", ".meson": "meson",
    ".md": "markdown", ".yml": "yaml", ".yaml": "yaml",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
    ".gif": "image", ".svg": "svg", ".gpg": "binary", ".pgp": "binary",
}


def role(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if path.suffix in {".patch", ".diff"}:
        return "upstream-patch"
    if name.startswith(("test_", "test-")) or "/tests/" in path.as_posix():
        return "verification"
    if suffix in {".md", ".log"}:
        return "documentation-or-record"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".gpg", ".pgp"}:
        return "asset-or-binary-input"
    if suffix in {".conf", ".desktop", ".json", ".lock", ".policy", ".rules", ".service", ".timer", ".toml", ".xml", ".yml", ".yaml", ".preset", ".feature", ".transfer", ".sources"}:
        return "configuration-or-data"
    if path.is_file() and path.stat().st_mode & 0o111:
        return "implementation"
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
            found.add(path.relative_to(ROOT))
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            found.add(path.relative_to(ROOT))
    return sorted(found, key=lambda path: path.as_posix())


def component_id(path: Path) -> str:
    """Assign a stable first-pass component group to each scoped file."""
    parts = path.parts
    if parts[0] == "mseries":
        directories = parts[1:-1]
        if directories[:1] == ("rust",):
            return "mseries/rust/" + (directories[1] if len(directories) > 1 else "migration-lane")
        if directories:
            return "mseries/" + "/".join(directories[:2])
        return "mseries/" + path.stem.lower()
    if parts[:2] == ("mkosi.images", "apple-silicon"):
        return "mseries/apple-silicon-image"
    if parts[:1] == ("mkosi.images",):
        return "elementary-os/image/" + parts[1]
    if parts[:2] == (".github", "workflows"):
        return "workflow/" + path.stem
    if parts[:1] == ("bin",):
        return "installer/" + path.name
    if parts[:1] == ("transform",):
        return "image-transform/" + path.name
    if parts[:1] == ("repos",):
        return "apt-repository/" + (parts[1] if len(parts) > 2 else path.stem)
    if parts[:1] == ("mkosi.conf.d",):
        return "image-build/profile/" + path.stem
    return "image-build/" + path.stem


def project_id(path: Path, ownership: str) -> str:
    """Join separately stored files that implement or verify one project."""
    text = path.as_posix()
    if ownership == "elementary-os-upstream":
        return "upstream/elementary/os"
    if text in PROJECT_PATH_OVERRIDES:
        return PROJECT_PATH_OVERRIDES[text]
    for prefix, project in PROJECT_PREFIX_OVERRIDES.items():
        if text.startswith(prefix):
            return project
    return component_id(path)


def render() -> str:
    items = []
    paths = source_paths()
    scoped_paths = {path.as_posix() for path in paths}
    stale_overrides = sorted(set(PROJECT_PATH_OVERRIDES) - scoped_paths)
    if stale_overrides:
        raise ValueError(f"project overrides refer to unscoped paths: {stale_overrides}")
    for prefix in PROJECT_PREFIX_OVERRIDES:
        if not any(path.startswith(prefix) for path in scoped_paths):
            raise ValueError(f"project prefix has no scoped files: {prefix}")
    for path in paths:
        text = path.as_posix()
        item_role = role(path)
        local = (
            text.startswith(("bin/", "transform/", "repos/", "mkosi.conf.d/", ".github/workflows/", "mseries/"))
            or text in ROOT_FILES
            or text.startswith("mkosi.images/apple-silicon/")
            or text in {
                "mkosi.images/liveiso/mkosi.conf.d/arch.arm64.conf",
                "mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf",
            }
        )
        ownership = "mseries-maintained" if local else "elementary-os-upstream"
        items.append({
            "id": text,
            "path": text,
            "component_id": component_id(path),
            "project_id": project_id(path, ownership),
            "ownership": ownership,
            "language": LANGUAGES.get(path.suffix.lower(), "binary-or-data" if not path.suffix else "data"),
            "role": item_role,
            "rust_status": (
                "candidate-functional-tests-passing-not-installed"
                if text.startswith(RUST_FUNCTIONAL_PREFIXES)
                else "candidate-parity-verified-not-installed"
                if text.startswith(RUST_CANDIDATE_PREFIXES)
                else "retain-upstream"
                if not local
                else "recorded-non-code-input"
                if item_role in {"documentation-or-record", "asset-or-binary-input"}
                else "not-assessed" if local else "retain-upstream"
            ),
        })
    component_groups: dict[str, list[dict[str, str]]] = {}
    for item in items:
        component_groups.setdefault(item["component_id"], []).append(item)
    components = []
    for component, records in sorted(component_groups.items()):
        components.append({
            "id": component,
            "ownership": records[0]["ownership"],
            "item_count": len(records),
            "rust_status_counts": {
                status: sum(record["rust_status"] == status for record in records)
                for status in sorted({record["rust_status"] for record in records})
            },
            "items": [record["id"] for record in records],
        })
    project_groups: dict[str, list[dict[str, str]]] = {}
    for item in items:
        project_groups.setdefault(item["project_id"], []).append(item)
    projects = []
    for project, records in sorted(project_groups.items()):
        owners = {record["ownership"] for record in records}
        if len(owners) != 1:
            raise ValueError(f"project {project} mixes ownership classes: {sorted(owners)}")
        projects.append({
            "id": project,
            "ownership": records[0]["ownership"],
            "item_count": len(records),
            "rust_status_counts": {
                status: sum(record["rust_status"] == status for record in records)
                for status in sorted({record["rust_status"] for record in records})
            },
            "items": [record["id"] for record in records],
        })
    document = {
        "schema": 2,
        "generated_by": "mseries/rust/inventory.py",
        "scope": list(DIRECTORIES) + list(ROOT_FILES),
        "item_count": len(items),
        "component_count": len(components),
        "project_count": len(projects),
        "components": components,
        "projects": projects,
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

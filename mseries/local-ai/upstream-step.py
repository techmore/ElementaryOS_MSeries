#!/usr/bin/env python3
"""Move a pinned upstream forward and re-apply the patches we carry on it (see upstreams.json).

  upstream-step.py status              pin vs upstream head for each upstream, and our patches
  upstream-step.py try NAME [REF]      fetch REF (default: what the step rule points at) and
                                       sort each patch: keep (applies), absorbed (upstream has
                                       it: drop ours), conflict (needs rework)
  upstream-step.py step NAME [REF]     try, then on no conflicts: move the pin in upstreams.json
                                       and install.sh, drop absorbed patches, rename versioned
                                       patch files, and print the build + gate commands

Only git runs on fetched source: nothing upstream is built or executed here. Building and the
MLX gate stay with the owner (install.sh, mlx-gate.py, engine-compare.py).
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "upstreams.json"
INSTALL = HERE / "install.sh"
# Never /tmp: it is RAM-backed on these machines.
CACHE = Path(os.environ.get("MSERIES_UPSTREAM_CACHE", Path.home() / ".cache/mseries-upstream"))


def load():
    return json.loads(MANIFEST.read_text())


def save(data):
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n")


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check)


def remote_head(repo, ref):
    out = git("ls-remote", f"https://github.com/{repo}.git", ref).stdout.split()
    return out[0] if out else None


def raw(repo, ref, path):
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read().decode()


def omarchy_mlx_lm_version(ref):
    m = re.search(r"^MLX_LM_VERSION=\"?([0-9.]+)", raw("joshuaswarren/omarchy-mlx", ref, "install.sh"), re.M)
    return m.group(1) if m else None


def target_ref(data, name):
    """The ref the step rule points at: the tracked branch head, or for mlx-lm the version
    our omarchy-mlx pin installs."""
    up = data["upstreams"][name]
    track = up.get("track")
    if track is None:
        raise SystemExit(f"{name} is stepped by hand; pass a REF")
    if track == "omarchy-mlx":
        # mlx-lm follows our omarchy-mlx pin: step omarchy-mlx first.
        version = omarchy_mlx_lm_version(data["upstreams"]["omarchy-mlx"]["pin"])
        return f"v{version}"
    return remote_head(up["repo"], f"refs/heads/{track}")


def fetch(repo, ref, dest):
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").is_dir():
        git("init", "-q", str(dest))
        git("remote", "add", "origin", f"https://github.com/{repo}.git", cwd=dest)
    git("fetch", "-q", "--depth", "1", "origin", ref, cwd=dest)
    git("checkout", "-q", "--force", "--detach", "FETCH_HEAD", cwd=dest)
    git("clean", "-qfdx", cwd=dest)
    return git("rev-parse", "HEAD", cwd=dest).stdout.strip()


def classify(tree, patch, strip=1):
    """keep / absorbed / conflict for one patch against a checked-out tree."""
    p = f"-p{strip}"
    if git("apply", "--check", p, str(patch), cwd=tree, check=False).returncode == 0:
        return "keep"
    if git("apply", "-R", "--check", p, str(patch), cwd=tree, check=False).returncode == 0:
        return "absorbed"
    return "conflict"


def try_ref(data, name, ref=None):
    up = data["upstreams"][name]
    ref = ref or target_ref(data, name)
    tree = CACHE / name
    sha = fetch(up["repo"], ref, tree)
    results = []
    # Patches stack in list order, so each kept one is applied before the next is tried.
    for entry in up["patches"]:
        state = classify(tree, HERE / entry["file"], up.get("strip", 1))
        if state == "keep":
            git("apply", f"-p{up.get('strip', 1)}", str(HERE / entry["file"]), cwd=tree)
        results.append((entry, state))
    print(f"{name}: {up['repo']} {ref} ({sha[:10]}), pinned {up.get('pin_label') or up['pin'][:10]}")
    if not results:
        print("  no patches carried")
    for entry, state in results:
        note = {"keep": "applies", "absorbed": "upstream has it: drop ours",
                "conflict": "does not apply: rework against this ref"}[state]
        print(f"  {state:9} {entry['file']}  ({entry['kind']}; {note})")
    return ref, sha, results


def versioned(name, old, new, path):
    """mlx-lm-0.31.3-x.patch -> mlx-lm-0.32.0-x.patch when the pin is a version tag."""
    o, n = old.lstrip("v"), new.lstrip("v")
    base = Path(path).name
    prefix = f"{name}-{o}-"
    if base.startswith(prefix) and re.fullmatch(r"[0-9.]+", n):
        return str(Path(path).with_name(f"{name}-{n}-" + base[len(prefix):]))
    return path


def step(data, name, ref=None):
    ref, sha, results = try_ref(data, name, ref)
    if any(state == "conflict" for _, state in results):
        raise SystemExit(f"\nNot stepped: rework the conflicting patches against {CACHE / name}, "
                         "commit them, and run step again.")
    up = data["upstreams"][name]
    old_pin = up["pin"]
    new_pin = ref if up.get("track") == "omarchy-mlx" else sha
    kept = []
    for entry, state in results:
        if state == "absorbed":
            (HERE / entry["file"]).unlink()
            for extra in entry.get("extra_files", []):
                (HERE / extra).unlink(missing_ok=True)
            print(f"  dropped {entry['file']}")
            continue
        new_file = versioned(name, old_pin, new_pin, entry["file"])
        if new_file != entry["file"]:
            (HERE / entry["file"]).rename(HERE / new_file)
            entry = {**entry, "file": new_file}
        kept.append(entry)
    up["patches"] = kept
    up["pin"] = new_pin
    up.pop("pin_label", None)
    checkout = up.get("install_checkout")
    if checkout:
        text = INSTALL.read_text()
        pattern = re.compile(rf"^(checkout {re.escape(checkout)} \S+ ){re.escape(old_pin)}$", re.M)
        text, n = pattern.subn(rf"\g<1>{new_pin}", text)
        if n != 1:
            raise SystemExit(f"install.sh has no single 'checkout {checkout}' line for {old_pin}")
        INSTALL.write_text(text)
    save(data)
    print(f"\nPinned {name} at {new_pin}. Next, on the laptop (the owner runs fetched-code builds):")
    print("  bash mseries/local-ai/install.sh            # rebuild with the new pin")
    print("  bash mseries/local-ai/serve-patch.sh build  # re-apply our mlx-lm patches")
    print("  python3 mseries/local-ai/mlx-gate.py sweep  # correctness gate")
    print("  python3 mseries/local-ai/engine-compare.py  # speed vs the old pin")
    print("If the gate fails or it is slower, `git checkout -- mseries/local-ai` undoes the step.")


def status(data):
    ups = data["upstreams"]
    for name, up in ups.items():
        line = f"{name:22} {up['repo']:38} pin {up.get('pin_label') or up['pin'][:10]}"
        try:
            if up.get("track") == "omarchy-mlx":
                head = omarchy_mlx_lm_version(ups["omarchy-mlx"]["track"])
                pinned = omarchy_mlx_lm_version(ups["omarchy-mlx"]["pin"])
                line += f"  omarchy-mlx installs {pinned}, its head {head}"
                line += "  <- step" if head != pinned else ""
            elif name == "omarchy-mlx":
                tags = git("ls-remote", "--tags", "--refs", f"https://github.com/{up['repo']}.git").stdout
                versions = sorted({t.rsplit("/", 1)[1] for t in tags.split() if re.search(r"/v[0-9.]+$", t)},
                                  key=lambda v: [int(x) for x in v[1:].split(".")])
                latest = versions[-1] if versions else "?"
                head_lm = omarchy_mlx_lm_version(up["track"])
                pin_lm = omarchy_mlx_lm_version(up["pin"])
                line += f"  latest release {latest}, head installs mlx-lm {head_lm}"
                if latest != up.get("pin_label") or head_lm != pin_lm:
                    line += "  <- step"
            elif up.get("track"):
                head = remote_head(up["repo"], f"refs/heads/{up['track']}")
                line += f"  {up['track']} {head[:10]}" + ("" if head == up["pin"] else "  (moved)")
            else:
                line += "  (stepped by hand)"
        except Exception as e:  # network trouble should not hide the rest
            line += f"  (could not reach upstream: {e})"
        print(line)
        for p in up["patches"]:
            if p.get("drop_when"):
                tag = f"{p['kind']}, drop when {p['drop_when']}"
            else:
                tag = p["kind"]
            print(f"    {Path(p['file']).name}: {tag}")


def main(argv):
    data = load()
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "status":
        status(data)
    elif cmd in ("try", "step") and rest and rest[0] in data["upstreams"]:
        (try_ref if cmd == "try" else step)(data, rest[0], rest[1] if len(rest) > 1 else None)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/bin/sh
set -eu

image="${1:?usage: $0 IMAGE}"

docker run --rm "$image" sh -ceu '
  uv lock --check
  uv pip freeze --python /app/.venv/bin/python > /tmp/image-freeze.txt
  python - <<'"'"'PY'"'"'
import tomllib


def normalize(name):
    return name.lower().replace("_", "-").replace(".", "-")


with open("uv.lock", "rb") as lock_file:
    lock = tomllib.load(lock_file)

locked = {}
for package in lock.get("package", []):
    name = normalize(package["name"])
    locked.setdefault(name, set()).add(package["version"])

installed = {}
for line in open("/tmp/image-freeze.txt", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("-e "):
        continue
    name, separator, version = line.partition("==")
    if not separator:
        raise SystemExit(f"Cannot parse freeze entry: {line!r}")
    if normalize(name) != "basic-adk-agent":
        installed[normalize(name)] = version

unexpected = sorted(name for name in installed if name not in locked)
mismatched = sorted(
    (name, version, sorted(locked[name]))
    for name, version in installed.items()
    if name in locked and version not in locked[name]
)
if unexpected or mismatched:
    print("Unexpected installed distributions:", unexpected)
    print("Versions absent from uv.lock:", mismatched)
    raise SystemExit(1)

print(f"Locked dependency check passed for {len(installed)} distributions")
PY
' 

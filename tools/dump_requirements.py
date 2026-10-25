#!/usr/bin/env python3
"""dump pyproject dependencies to a requirements file for platforms without uv."""

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
DEFAULT_OUTPUT = ROOT / "requirements.txt"
EXTRAS = ("webui", "channels", "modules")
HEADER = "# generated from pyproject.toml by tools/dump_requirements.py; do not edit\n"


def render():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    deps = list(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    for extra in EXTRAS:
        deps.extend(optional.get(extra, []))
    # keep pyproject order, drop duplicates
    return HEADER + "".join(f"{dep}\n" for dep in dict.fromkeys(deps))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail if the output file is out of date")
    args = parser.parse_args()

    content = render()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current != content:
            print(f"{args.output} is out of date; run tools/dump_requirements.py", file=sys.stderr)
            return 1
        return 0

    args.output.write_text(content, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

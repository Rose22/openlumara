#!/usr/bin/env python3
"""dump pyproject dependencies to a requirements file for platforms without uv.

by default only the required dependencies are written; --groups adds optional ones.
"""

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
DEFAULT_OUTPUT = ROOT / "requirements.txt"


def read_project():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def parse_groups(raw, optional):
    """comma-separated group names -> ordered, deduped list of known groups."""
    groups = []
    for name in (part.strip() for part in raw.split(",")):
        if not name:
            continue
        if name not in optional:
            known = ", ".join(sorted(optional))
            raise SystemExit(f"unknown group '{name}' (known groups: {known})")
        if name not in groups:
            groups.append(name)
    return groups


def render(project, groups):
    deps = list(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    for group in groups:
        deps.extend(optional[group])
    note = f"groups: {', '.join(groups)}" if groups else "required only"
    header = f"# generated from pyproject.toml by tools/dump_requirements.py ({note}); do not edit\n"
    # keep pyproject order, drop duplicates
    return header + "".join(f"{dep}\n" for dep in dict.fromkeys(deps))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--groups",
        default="",
        help="comma-separated optional-dependency groups to add (e.g. webui,channels,modules)",
    )
    parser.add_argument("--check", action="store_true", help="fail if the output file is out of date")
    args = parser.parse_args()

    project = read_project()
    groups = parse_groups(args.groups, project.get("optional-dependencies", {}))
    content = render(project, groups)

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current != content:
            hint = f" --groups {','.join(groups)}" if groups else ""
            print(f"{args.output} is out of date; run tools/dump_requirements.py{hint}", file=sys.stderr)
            return 1
        return 0

    args.output.write_text(content, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

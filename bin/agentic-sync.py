#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"

def discover_core_skills(framework_root: Path) -> list[str]:
    skills_dir = framework_root / ".agentic" / "skills"

    if not skills_dir.exists():
        return []

    skills = []
    for path in skills_dir.iterdir():
        if path.is_dir() and (path / "SKILL.md").exists():
            skills.append(path.name)

    return sorted(skills)

def find_framework_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def build_managed_files(core_skills: list[str]) -> list[str]:
    files: list[str] = [
        "docs/documentation-methodology.md",
    ]

    for skill in core_skills:
        files.extend(
            [
                f".agentic/skills/{skill}/SKILL.md",
                f".claude/skills/{skill}/SKILL.md",
                f".opencode/skills/{skill}/SKILL.md",
            ]
        )

    return files

def validate_basic_target(framework_root: Path, target: Path) -> bool:
    if not is_git_repo(framework_root):
        print(f"ERROR: framework root is not a git repository: {framework_root}", file=sys.stderr)
        return False

    if not is_git_repo(target):
        print(f"ERROR: target is not a git repository: {target}", file=sys.stderr)
        return False

    if target == framework_root:
        print("ERROR: target cannot be the framework repository itself.", file=sys.stderr)
        return False

    conflicting_paths = [
        ".agentic",
        ".agentic.lock.json",
    ]

    conflicts = [path for path in conflicting_paths if (target / path).exists()]

    if conflicts:
        print("ERROR: target already contains agentic-related paths:", file=sys.stderr)
        for path in conflicts:
            print(f"  - {path}", file=sys.stderr)
        print("Refusing to continue to avoid overwriting existing files.", file=sys.stderr)
        return False

    return True

def file_status(source: Path, destination: Path) -> str:
    if not source.exists():
        return "MISSING"
    if not destination.exists():
        return "INSTALL"
    if source.read_bytes() == destination.read_bytes():
        return "SKIP"
    return "CONFLICT"


def summarize_statuses(statuses: list[str]) -> dict[str, int]:
    summary = {
        "INSTALL": 0,
        "SKIP": 0,
        "CONFLICT": 0,
        "MISSING": 0,
    }

    for status in statuses:
        summary[status] += 1

    return summary

def print_plan(framework_root: Path, target: Path, core_skills: list[str]) -> None:
    managed_files = build_managed_files(core_skills)

    print("Agentic Repo Framework: OK")
    print("Target repository: OK")
    print("No framework conflicts detected")
    print()
    print(f"Framework version: {VERSION}")
    print(f"Framework root: {framework_root}")
    print(f"Target: {target}")
    print()

    print("Core skills:")
    for skill in core_skills:
        print(f"  - {skill}")
    print()

    print("Files:")
    statuses: list[str] = []

    for file_path in managed_files:
        source = framework_root / file_path
        destination = target / file_path
        status = file_status(source, destination)
        statuses.append(status)
        print(f"  - {file_path} [{status}]")

    summary = summarize_statuses(statuses)

    print()
    print("Summary:")
    print(f"  install: {summary['INSTALL']}")
    print(f"  skip: {summary['SKIP']}")
    print(f"  conflict: {summary['CONFLICT']}")
    print(f"  missing source: {summary['MISSING']}")

    if summary["CONFLICT"] > 0:
        print()
        print("Note: conflicting files will be left untouched by --apply.")

    if summary["MISSING"] > 0:
        print()
        print("Note: missing source files cannot be installed. Try a git pull in the framework repository to ensure you have the latest version.")

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install/update Agentic Repo Framework components in a target repo."
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show what would be installed without changing the target repository.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target repository path. Defaults to current directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install/update safe files in the target repository.",
    )

    args = parser.parse_args()

    framework_root = find_framework_root()
    target = Path(args.target).resolve()

    if not validate_basic_target(framework_root, target):
        return 1

    core_skills = discover_core_skills(framework_root)

    if args.plan:
        print_plan(framework_root, target, core_skills)
        return 0

    if args.apply:
        return apply_plan(framework_root, target, core_skills)

    print("Agentic Repo Framework: OK")
    print("Target repository: OK")
    print("No framework conflicts detected")
    print()
    print(f"Framework version: {VERSION}")
    print(f"Framework root: {framework_root}")
    print(f"Target: {target}")
    print()
    print("No action selected. Use --plan to preview installation.")

    return 0

def apply_plan(framework_root: Path, target: Path, core_skills: list[str]) -> int:
    managed_files = build_managed_files(core_skills)

    installed = 0
    skipped = 0
    conflicts = 0
    missing = 0

    for file_path in managed_files:
        source = framework_root / file_path
        destination = target / file_path
        status = file_status(source, destination)

        if status == "INSTALL":
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            installed += 1
            print(f"INSTALL  {file_path}")
        elif status == "SKIP":
            skipped += 1
            print(f"SKIP     {file_path}")
        elif status == "CONFLICT":
            conflicts += 1
            print(f"CONFLICT {file_path}")
        elif status == "MISSING":
            missing += 1
            print(f"MISSING  {file_path}")

    lockfile = {
        "framework_version": VERSION,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source": str(framework_root),
        "managed_core_skills": core_skills,
        "managed_files": managed_files,
    }

    lockfile_path = target / ".agentic.lock.json"
    lockfile_path.write_text(json.dumps(lockfile, indent=2) + "\n", encoding="utf-8")
    print(f"WRITE    .agentic.lock.json")

    print()
    print("Summary:")
    print(f"  installed: {installed}")
    print(f"  skipped: {skipped}")
    print(f"  conflicts left untouched: {conflicts}")
    print(f"  missing sources: {missing}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
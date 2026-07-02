#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_FILE = ".agentic-framework.json"


def find_framework_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def load_manifest(framework_root: Path) -> dict:
    manifest_path = framework_root / MANIFEST_FILE

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing framework manifest: {manifest_path}")

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def discover_core_skills(framework_root: Path) -> list[str]:
    skills_dir = framework_root / ".agentic" / "skills"

    if not skills_dir.exists():
        return []

    skills: list[str] = []

    for path in skills_dir.iterdir():
        if path.is_dir() and (path / "SKILL.md").exists():
            skills.append(path.name)

    return sorted(skills)


def discover_managed_skill_files(framework_root: Path, skill_roots: list[str]) -> list[str]:
    files: list[str] = []

    for root in skill_roots:
        root_path = framework_root / root

        if not root_path.exists():
            continue

        for skill_file in sorted(root_path.glob("*/SKILL.md")):
            files.append(str(skill_file.relative_to(framework_root)))

    return files


def build_managed_files(framework_root: Path, manifest: dict) -> list[str]:
    files: list[str] = list(manifest.get("managed_files", []))

    files.extend(
        discover_managed_skill_files(
            framework_root,
            manifest.get("managed_skill_roots", []),
        )
    )

    return sorted(files)


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


def print_header(framework_root: Path, target: Path, version: str) -> None:
    print("Agentic Repo Framework: OK")
    print("Target repository: OK")
    print("No framework conflicts detected")
    print()
    print(f"Framework version: {version}")
    print(f"Framework root: {framework_root}")
    print(f"Target: {target}")
    print()


def print_plan(framework_root: Path, target: Path, manifest: dict) -> None:
    version = manifest["framework_version"]
    core_skills = discover_core_skills(framework_root)
    managed_files = build_managed_files(framework_root, manifest)

    print_header(framework_root, target, version)

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
        print(
            "Note: missing source files cannot be installed. "
            "Try a git pull in the framework repository to ensure you have the latest version."
        )


def apply_plan(framework_root: Path, target: Path, manifest: dict) -> int:
    version = manifest["framework_version"]
    core_skills = discover_core_skills(framework_root)
    managed_files = build_managed_files(framework_root, manifest)

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
        "framework_version": version,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source": str(framework_root),
        "managed_core_skills": core_skills,
        "managed_files": managed_files,
    }

    lockfile_path = target / ".agentic.lock.json"
    lockfile_path.write_text(json.dumps(lockfile, indent=2) + "\n", encoding="utf-8")
    print("WRITE    .agentic.lock.json")

    print()
    print("Summary:")
    print(f"  installed: {installed}")
    print(f"  skipped: {skipped}")
    print(f"  conflicts left untouched: {conflicts}")
    print(f"  missing sources: {missing}")

    return 0


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
        "--apply",
        action="store_true",
        help="Install/update safe files in the target repository.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target repository path. Defaults to current directory.",
    )

    args = parser.parse_args()

    framework_root = find_framework_root()
    target = Path(args.target).resolve()

    try:
        manifest = load_manifest(framework_root)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not validate_basic_target(framework_root, target):
        return 1

    if args.plan:
        print_plan(framework_root, target, manifest)
        return 0

    if args.apply:
        return apply_plan(framework_root, target, manifest)

    print_header(framework_root, target, manifest["framework_version"])
    print("No action selected. Use --plan to preview installation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
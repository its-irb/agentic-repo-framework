#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_FILE = ".agentic-framework.json"

def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file, reading in 1 MB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_target_lockfile(target: Path) -> dict:
    """Load the consumer lockfile (.agentic.lock.json) from a target repository.

    Returns an empty dict if the lockfile does not exist. The lockfile records
    which framework-managed files were installed, their SHA-256 hashes, and the
    framework version, enabling the sync tool to distinguish safe updates from
    genuine conflicts.

    The lockfile is shared with other components (e.g. docs-init, docs-update),
    which may store their own top-level keys (such as ``documentation``). This
    function only parses the file; it never rewrites it.

    Raises ValueError if the lockfile exists but is not valid JSON or its root
    is not a JSON object. In that case the caller must halt without overwriting
    the file, so the user can fix it manually.
    """
    lockfile_path = target / ".agentic.lock.json"
    if not lockfile_path.exists():
        return {}

    try:
        data = json.loads(lockfile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{lockfile_path} contains invalid JSON "
            f"({exc.msg} at line {exc.lineno} column {exc.colno}). "
            f"Fix it manually; agentic-sync will not overwrite it."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"{lockfile_path} root is not a JSON object "
            f"(got {type(data).__name__}). "
            f"Fix it manually; agentic-sync will not overwrite it."
        )

    return data

def get_locked_hash(lockfile: dict, file_path: str) -> str | None:
    """Return the SHA-256 hash stored in the lockfile for a given managed file.

    Returns None if the file is not present in the lockfile or the lockfile
    structure does not contain managed_files. This hash is used to determine
    whether a divergent destination file represents a safe UPDATE (matches the
    lockfile) or a genuine CONFLICT (does not match).
    """
    managed_files = lockfile.get("managed_files", {})

    if isinstance(managed_files, dict):
        entry = managed_files.get(file_path)
        if isinstance(entry, dict):
            return entry.get("sha256")

    return None

def find_framework_root() -> Path:
    """Resolve the framework root directory as the grandparent of this script."""
    return Path(__file__).resolve().parent.parent


def is_git_repo(path: Path) -> bool:
    """Check whether a directory is a git repository by testing for .git."""
    return (path / ".git").exists()


def load_manifest(framework_root: Path) -> dict:
    """Load and parse the framework manifest (.agentic-framework.json).

    The manifest declares the framework version, explicit managed_files, and
    managed_skill_roots (directories to scan for skill SKILL.md files).

    Raises FileNotFoundError if the manifest does not exist.
    """
    manifest_path = framework_root / MANIFEST_FILE

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing framework manifest: {manifest_path}")

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def discover_core_skills(framework_root: Path) -> list[str]:
    """Discover core skills by scanning .agentic/skills/ for directories with a SKILL.md.

    Core skills are the shared implementations maintained by the framework.
    Returns a sorted list of skill directory names (e.g. ["commit-work", "docs-init"]).
    """
    skills_dir = framework_root / ".agentic" / "skills"

    if not skills_dir.exists():
        return []

    skills: list[str] = []

    for path in skills_dir.iterdir():
        if path.is_dir() and (path / "SKILL.md").exists():
            skills.append(path.name)

    return sorted(skills)


def discover_managed_skill_files(framework_root: Path, skill_roots: list[str]) -> list[str]:
    """Discover wrapper skill files by scanning each skill_root for */SKILL.md.

    Wrapper skills (e.g. under .claude/skills/ or .opencode/skills/) are
    platform-specific files that delegate to the core implementation. Each
    skill_root is globbed for any SKILL.md under a subdirectory.

    Returns a sorted list of relative file paths.
    """
    files: list[str] = []

    for root in skill_roots:
        root_path = framework_root / root

        if not root_path.exists():
            continue

        for skill_file in sorted(root_path.glob("*/SKILL.md")):
            files.append(str(skill_file.relative_to(framework_root)))

    return files


def build_managed_files(framework_root: Path, manifest: dict) -> list[str]:
    """Build the complete sorted list of managed file paths.

    Combines explicit managed_files from the manifest with discovered skill
    files from all managed_skill_roots. These are the files that agentic-sync
    will install or update in the target repository.
    """
    files: list[str] = list(manifest.get("managed_files", []))

    files.extend(
        discover_managed_skill_files(
            framework_root,
            manifest.get("managed_skill_roots", []),
        )
    )

    return sorted(files)


def validate_basic_target(framework_root: Path, target: Path) -> bool:
    """Validate that both framework root and target are git repositories.

    Checks that:
    - The framework root is a git repository.
    - The target is a git repository.
    - The target is not the same as the framework root.

    Returns True if all checks pass. Prints errors to stderr and returns False
    on failure.
    """
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


def file_status(source: Path, destination: Path, locked_hash: str | None) -> str:
    """Determine the sync status of a single managed file.

    Compares the source file (in the framework), the destination file (in the
    target), and the locked hash (from the target's lockfile) to classify the
    file into one of five states:

    - MISSING: source file does not exist in the framework repo.
    - INSTALL: source exists, destination does not. Needs to be copied.
    - SKIP: source and destination have identical SHA-256 hashes. Already in sync.
    - UPDATE: destination differs from source but matches the locked hash. The
      file was intentionally modified after installation and the framework now
      has a newer version. Safe to update.
    - CONFLICT: destination differs from both the source and the locked hash.
      Someone made untracked local changes. Left untouched unless --force.

    Returns one of: "MISSING", "INSTALL", "SKIP", "UPDATE", "CONFLICT".
    """
    if not source.exists():
        return "MISSING"

    if not destination.exists():
        return "INSTALL"

    source_hash = sha256_file(source)
    destination_hash = sha256_file(destination)

    if destination_hash == source_hash:
        return "SKIP"

    if locked_hash is not None and destination_hash == locked_hash:
        return "UPDATE"

    return "CONFLICT"


def summarize_statuses(statuses: list[str]) -> dict[str, int]:
    """Count occurrences of each file status and return a summary dict.

    Returns a dict with keys INSTALL, UPDATE, SKIP, CONFLICT, and MISSING,
    each mapping to the number of files with that status.
    """
    summary = {
        "INSTALL": 0,
        "UPDATE": 0,
        "SKIP": 0,
        "CONFLICT": 0,
        "MISSING": 0,
    }

    for status in statuses:
        summary[status] += 1

    return summary


def print_header(framework_root: Path, target: Path, version: str) -> None:
    """Print the sync header confirming both repos are valid.

    Displays confirmation that the framework root and target repository are OK,
    no conflicts have been detected yet, and basic metadata (version, paths).
    """
    print("Agentic Repo Framework: OK")
    print("Target repository: OK")
    print("No framework conflicts detected")
    print()
    print(f"Framework version: {version}")
    print(f"Framework root: {framework_root}")
    print(f"Target: {target}")
    print()


def print_plan(framework_root: Path, target: Path, manifest: dict) -> None:
    """Preview what agentic-sync would install without modifying the target repository.

    Discovers core skills and managed files from the manifest, computes the sync
    status of each file (INSTALL, UPDATE, SKIP, CONFLICT, MISSING), prints each
    file with its status tag, and displays a summary. Warns about conflicts and
    missing source files.

    This is the read-only mode invoked by --plan.
    """
    version = manifest["framework_version"]
    core_skills = discover_core_skills(framework_root)
    managed_files = build_managed_files(framework_root, manifest)
    target_lockfile = load_target_lockfile(target)

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
        locked_hash = get_locked_hash(target_lockfile, file_path)
        status = file_status(source, destination, locked_hash)
        statuses.append(status)
        print(f"  - {file_path} [{status}]")

    summary = summarize_statuses(statuses)

    print()
    print("Summary:")
    print(f"  install: {summary['INSTALL']}")
    print(f"  update: {summary['UPDATE']}")
    print(f"  skip: {summary['SKIP']}")
    print(f"  conflict: {summary['CONFLICT']}")
    print(f"  missing source: {summary['MISSING']}")

    if summary["CONFLICT"] > 0:
        print()
        print("Note: conflicting files will be left untouched by --apply unless --force is used.")

    if summary["MISSING"] > 0:
        print()
        print(
            "Note: missing source files cannot be installed. "
            "Try a git pull in the framework repository to ensure you have the latest version."
        )


def apply_plan(framework_root: Path, target: Path, manifest: dict, force: bool) -> int:
    """Install or update framework-managed files in the target repository.

    For each managed file, determines its status and performs the appropriate
    action:
    - INSTALL: copies the file to the target.
    - UPDATE: overwrites the file (safe because it matches the locked hash).
    - SKIP: leaves the file alone (already in sync).
    - CONFLICT: leaves the file alone unless --force is given.
    - MISSING: skips (source does not exist in the framework).

    Builds a new .agentic.lock.json in the target with updated hashes and
    writes it to disk. Returns exit code 0 on success.

    This is the write mode invoked by --apply.
    """
    version = manifest["framework_version"]
    core_skills = discover_core_skills(framework_root)
    managed_files = build_managed_files(framework_root, manifest)
    target_lockfile = load_target_lockfile(target)
    new_managed_files: dict[str, dict[str, str]] = {}

    installed = 0
    updated = 0
    forced = 0
    skipped = 0
    conflicts = 0
    missing = 0

    for file_path in managed_files:
        source = framework_root / file_path
        destination = target / file_path
        locked_hash = get_locked_hash(target_lockfile, file_path)
        status = file_status(source, destination, locked_hash)

        if status == "INSTALL":
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            new_managed_files[file_path] = {"sha256": sha256_file(source)}
            installed += 1
            print(f"INSTALL  {file_path}")

        elif status == "UPDATE":
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            new_managed_files[file_path] = {"sha256": sha256_file(source)}
            updated += 1
            print(f"UPDATE   {file_path}")

        elif status == "SKIP":
            new_managed_files[file_path] = {"sha256": sha256_file(source)}
            skipped += 1
            print(f"SKIP     {file_path}")

        elif status == "CONFLICT":
            if force:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                new_managed_files[file_path] = {"sha256": sha256_file(source)}
                forced += 1
                print(f"FORCE    {file_path}")
            else:
                if locked_hash is not None:
                    new_managed_files[file_path] = {"sha256": locked_hash}
                conflicts += 1
                print(f"CONFLICT {file_path}")

        elif status == "MISSING":
            missing += 1
            print(f"MISSING  {file_path}")

    # The lockfile is shared with other components (e.g. docs-init/docs-update
    # own the ``documentation`` key). Preserve every existing top-level key and
    # update only the keys managed by agentic-sync. Start from a shallow copy of
    # the current lockfile (empty dict when the file did not exist).
    lockfile = dict(target_lockfile)
    lockfile["framework_version"] = version
    lockfile["installed_at"] = datetime.now(timezone.utc).isoformat()
    lockfile["source"] = str(framework_root)
    lockfile["managed_core_skills"] = core_skills
    lockfile["managed_files"] = new_managed_files

    # Atomic write: serialize the full JSON first, then write to a temp file in
    # the same directory and replace the original only after success.
    lockfile_path = target / ".agentic.lock.json"
    content = json.dumps(lockfile, indent=2) + "\n"
    tmp_path = lockfile_path.with_name(lockfile_path.name + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, lockfile_path)
    print("WRITE    .agentic.lock.json")

    print()
    print("Summary:")
    print(f"  installed: {installed}")
    print(f"  updated: {updated}")
    print(f"  forced: {forced}")
    print(f"  skipped: {skipped}")
    print(f"  conflicts left untouched: {conflicts}")
    print(f"  missing sources: {missing}")

    return 0


def main() -> int:
    """Entry point: parse CLI args, validate, and dispatch to --plan or --apply.

    Supported arguments:
      --plan    Preview what would be installed without changing the target.
      --apply   Install/update files in the target repository.
      --force   Overwrite conflicting files with framework versions (used with --apply).
      target    Target repository path (default: current directory).

    Returns 0 on success, 1 on error.
    """
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite conflicting managed files with framework versions.",
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
        try:
            print_plan(framework_root, target, manifest)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.apply:
        try:
            return apply_plan(framework_root, target, manifest, args.force)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print_header(framework_root, target, manifest["framework_version"])
    print("No action selected. Use --plan to preview installation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
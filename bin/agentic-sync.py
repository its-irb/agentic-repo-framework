#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import hashlib
import urllib.parse
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


def _run_git(cwd: Path, args: list[str]) -> tuple[int, str]:
    """Run a read-only git command in ``cwd`` and return (returncode, stdout).

    stdout is stripped of surrounding whitespace. stderr is captured and
    discarded: callers rely on the return code to detect failure and craft
    their own error messages. Used only for git introspection of the framework
    repository.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def _parse_github_remote(url: str) -> tuple[str, str] | None:
    """Parse a GitHub remote URL into an ``(owner, repo)`` pair.

    Supports the common GitHub remote formats:

    - SSH scp-like:     ``git@github.com:owner/repo.git``
    - SSH explicit:     ``ssh://git@github.com/owner/repo.git``
    - HTTPS:            ``https://github.com/owner/repo.git``
                        ``https://github.com/owner/repo``

    Returns None for any other host (GitLab, self-hosted, etc.) or a URL that
    does not match one of these forms. The returned ``repo`` never carries the
    trailing ``.git`` suffix. The owner/repo segments are URL-decoded so values
    containing percent-escapes are handled, and segments are kept verbatim
    (case preserved).

    This validates that the configured origin is a GitHub remote before the
    canonical resolution attempts any network call.
    """
    candidates: list[tuple[str, str, str]] = []

    # SSH scp-like: git@github.com:owner/repo.git  (also git@github.com:owner/repo)
    # The user/host part is optional; the separator is ':'.
    m = re.match(r"^(?:[^@\s]+@)?github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        candidates.append((urllib.parse.unquote(m.group(1)),
                           urllib.parse.unquote(m.group(2)),
                           "scp"))

    # SSH explicit: ssh://[user@]github.com/owner/repo.git
    # HTTPS:        https://[user:pass@]github.com/owner/repo.git
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.scheme in ("ssh", "https") \
            and parsed.hostname == "github.com":
        parts = [p for p in parsed.path.split("/") if p != ""]
        if len(parts) == 2:
            owner = urllib.parse.unquote(parts[0])
            repo = urllib.parse.unquote(parts[1])
            if repo.endswith(".git"):
                repo = repo[: -len(".git")]
            candidates.append((owner, repo, parsed.scheme))

    for owner, repo, _kind in candidates:
        if owner != "" and repo != "":
            return owner, repo
    return None


def _ssh_to_https(url: str) -> str | None:
    """Convert a GitHub SSH remote URL to its HTTPS equivalent.

    Supports:
    - SSH scp-like:  ``git@github.com:owner/repo.git``  (with optional user@)
    - SSH explicit:  ``ssh://[user@]github.com/owner/repo.git``

    Returns the HTTPS URL ``https://github.com/owner/repo.git`` (always with a
    trailing ``.git``), or None if ``url`` is not a GitHub SSH remote. HTTPS
    URLs are passed through unchanged by the caller (not handled here).
    """
    # SSH scp-like: [user@]github.com:owner/repo[.git]
    m = re.match(r"^(?:[^@\s]+@)?github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        owner = urllib.parse.unquote(m.group(1))
        repo = urllib.parse.unquote(m.group(2))
        return f"https://github.com/{owner}/{repo}.git"

    # SSH explicit: ssh://[user@]github.com/owner/repo[.git]
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if parsed.scheme == "ssh" and parsed.hostname == "github.com":
        parts = [p for p in parsed.path.split("/") if p != ""]
        if len(parts) == 2:
            owner = urllib.parse.unquote(parts[0])
            repo = urllib.parse.unquote(parts[1])
            if repo.endswith(".git"):
                repo = repo[: -len(".git")]
            return f"https://github.com/{owner}/{repo}.git"

    return None


# Matches the git stderr line emitted when an HTTP redirect is followed:
#   warning: redirecting to https://github.com/<owner>/<repo>.git/
# Captures the raw URL token (validated/normalized separately). Tolerant of a
# trailing slash; the URL may or may not end with ``.git``.
_REDIRECT_WARNING_RE = re.compile(
    r"^warning: redirecting to (\S+)\s*$",
    re.MULTILINE,
)


def _normalize_github_https(url: str) -> str:
    """Validate and normalize a GitHub HTTPS URL to canonical git form.

    Accepts ``https://github.com/<owner>/<repo>`` with or without a trailing
    ``.git`` and with or without a trailing ``/``. Returns the canonical form
    ``https://github.com/<owner>/<repo>.git``. Raises ValueError if the URL is
    not a valid GitHub HTTPS repository URL (wrong host, too few segments,
    empty owner/repo, or a non-HTTPS scheme).
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise ValueError(
            f"Cannot interpret GitHub URL {url!r}: invalid URL ({exc})."
        ) from exc

    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ValueError(
            f"Cannot interpret GitHub URL {url!r}: not an HTTPS URL on "
            f"github.com (scheme={parsed.scheme!r}, host={parsed.hostname!r})."
        )

    parts = [p for p in parsed.path.split("/") if p != ""]
    if len(parts) < 2:
        raise ValueError(
            f"Cannot interpret GitHub URL {url!r}: missing owner/repo segments."
        )

    owner = urllib.parse.unquote(parts[0])
    repo = urllib.parse.unquote(parts[1])
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    if owner == "" or repo == "":
        raise ValueError(
            f"Cannot interpret GitHub URL {url!r}: empty owner or repo."
        )

    return f"https://github.com/{owner}/{repo}.git"


def _run_git_lsremote(https_url: str) -> tuple[int, str, str]:
    """Run ``git ls-remote <url> HEAD`` in a controlled environment.

    Returns ``(returncode, stdout, stderr)``. The environment forces
    ``LC_ALL=C`` so any parsed message has a stable English format, and
    ``GIT_TERMINAL_PROMPT=0`` so git never blocks waiting for credentials
    interactively (a non-interactive failure is preferable to a hang).

    This reuses Git's own HTTPS transport, TLS configuration and credentials
    already available on the machine, instead of relying on the Python
    interpreter's certificate bundle.
    """
    env = {**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ["git", "ls-remote", https_url, "HEAD"],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _resolve_github_canonical(configured_url: str) -> str:
    """Resolve the canonical GitHub location of a repository via git ls-remote.

    The configured ``origin`` URL is the **starting point**. If it is an SSH
    GitHub URL, it is converted to its HTTPS equivalent for the remote query
    (the framework repository is public, so HTTPS access works without
    credentials). ``git ls-remote <url> HEAD`` is then executed.

    Git follows HTTP redirects issued by GitHub (e.g. after a repository
    transfer) and emits on stderr, for each redirect, a line of the form::

        warning: redirecting to https://github.com/<owner>/<repo>.git/

    If one or more such warnings appear, the **last** redirect URL is the final
    destination and is used as the canonical URL. If no warning appears and
    ``git ls-remote`` succeeds, the queried URL itself is canonical.

    The result is always normalized to ``https://github.com/<owner>/<repo>.git``.

    Raises ValueError with a clear message if:
    - the configured URL is not a GitHub remote (SSH or HTTPS on github.com);
    - ``git ls-remote`` fails (non-zero exit; includes network, TLS, auth, or
      nonexistent-repository errors);
    - a redirect warning points to a URL that is not a valid GitHub HTTPS
      repository URL;
    - the final URL cannot be normalized.

    No value is fabricated: callers must abort the sync on failure.
    """
    parsed = _parse_github_remote(configured_url)
    if parsed is None:
        raise ValueError(
            f"Cannot determine the framework canonical remote URL reliably: "
            f"the configured 'origin' URL {configured_url!r} is not a "
            f"supported GitHub remote (SSH or HTTPS on github.com). "
            f"agentic-sync only resolves GitHub origins."
        )

    # Use HTTPS for the remote query. SSH URLs are converted; HTTPS URLs are
    # normalized (accepts with/without .git and trailing slash).
    if configured_url.startswith("https://"):
        query_url = _normalize_github_https(configured_url)
    else:
        converted = _ssh_to_https(configured_url)
        if converted is None:
            raise ValueError(
                f"Cannot determine the framework canonical remote URL reliably: "
                f"the configured 'origin' URL {configured_url!r} could not be "
                f"converted to HTTPS for remote resolution."
            )
        query_url = converted

    rc, _stdout, stderr = _run_git_lsremote(query_url)
    if rc != 0:
        detail = stderr.strip()
        if len(detail) > 400:
            detail = detail[:400] + "..."
        raise ValueError(
            f"Cannot resolve the canonical GitHub URL for "
            f"{query_url!r}: git ls-remote failed (exit {rc}). "
            f"The repository may be private, deleted, or the network/TLS "
            f"configuration may be blocking access. "
            f"agentic-sync will not write an unverified URL. "
            f"git output: {detail}"
        )

    # Extract redirect URLs from stderr. If multiple redirects occurred, the
    # last one is the final destination.
    redirects = _REDIRECT_WARNING_RE.findall(stderr)
    if redirects:
        final_url = redirects[-1]
    else:
        final_url = query_url

    return _normalize_github_https(final_url)


def resolve_framework_origin(framework_root: Path) -> dict[str, str]:
    """Resolve the canonical origin of the framework repo for traceability.

    Returns a dict with three keys describing the exact source and revision of
    the framework that ``apply_plan`` will record in the target's lockfile on a
    successful ``--apply``:

    - ``framework_remote_url``: canonical GitHub git URL of the framework
      repository, resolved from the locally configured ``origin`` remote. The
      configured URL is only the **starting point**: it is converted to HTTPS
      (if SSH) and ``git ls-remote`` is run against it. Git follows GitHub's
      HTTP redirects (e.g. after a transfer) and the final redirect URL, or the
      queried URL if no redirect occurs, is recorded. Thus a transferred
      repository (old URL still configured locally but GitHub redirects to the
      new location) yields the new canonical URL. The value is normalized to
      ``https://github.com/<owner>/<repo>.git``. Re-resolved on every sync, so
      the stored value is always replaced with the current canonical location.
    - ``framework_branch``: branch currently checked out in the framework
      repository. A detached HEAD is rejected.
    - ``framework_commit``: full SHA of HEAD in the framework repository.

    Raises ValueError with a clear message if any of the three cannot be
    determined reliably. This covers: missing ``origin`` remote, detached HEAD,
    empty repository with no commits, non-GitHub remote URL, ``git ls-remote``
    failure (network, TLS, auth, nonexistent repo), or an unnormalizable final
    URL. ``apply_plan`` calls this before touching the target, so an unreliable
    origin halts the sync without leaving partial state and without writing
    fabricated or ambiguous data to the lockfile.
    """
    rc, branch = _run_git(framework_root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if rc != 0 or not branch:
        raise ValueError(
            f"Cannot determine the framework branch reliably: HEAD is detached "
            f"or unreadable in {framework_root}. "
            f"Checkout a branch in the framework repository before syncing."
        )

    rc, commit = _run_git(framework_root, ["rev-parse", "--verify", "HEAD"])
    if rc != 0 or not commit:
        raise ValueError(
            f"Cannot determine the framework commit reliably: HEAD has no "
            f"commits in {framework_root}. "
            f"Commit something in the framework repository before syncing."
        )

    rc, configured_url = _run_git(framework_root, ["remote", "get-url", "origin"])
    if rc != 0 or not configured_url:
        raise ValueError(
            f"Cannot determine the framework remote URL reliably: "
            f"no 'origin' remote configured in {framework_root}. "
            f"Configure an 'origin' remote before syncing."
        )

    canonical_url = _resolve_github_canonical(configured_url)

    return {
        "framework_remote_url": canonical_url,
        "framework_branch": branch,
        "framework_commit": commit,
    }



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

    Before touching the target, validates the existing lockfile
    (``load_target_lockfile``) and then resolves the framework origin (canonical
    remote URL, branch, commit) via ``resolve_framework_origin``. Resolving the
    origin may require network access to verify the canonical GitHub URL, so the
    lockfile is validated first to fail fast on a corrupt lockfile without
    hitting the network. If the framework git state or the canonical URL cannot
    be determined reliably, apply halts with a ValueError and the target's
    lockfile is left untouched. On success the lockfile records the resolved
    origin as the traceability of the last successful apply.

    This is the write mode invoked by --apply.
    """
    version = manifest["framework_version"]
    core_skills = discover_core_skills(framework_root)
    managed_files = build_managed_files(framework_root, manifest)
    # Validate the existing lockfile first (cheap, local) so a corrupt lockfile
    # halts before any network call. Then resolve the framework origin, which
    # may issue an HTTP request to verify the canonical GitHub URL. If either
    # step fails, apply halts without copying any file and without rewriting
    # the lockfile, so the lock never claims a commit that was not applied.
    target_lockfile = load_target_lockfile(target)
    origin = resolve_framework_origin(framework_root)
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
    # Traceability of the last successful apply: exact origin and revision of
    # the framework used. Re-read from the framework git repo on every sync, so
    # these values replace any previously stored ones (e.g. after a transfer to
    # a new remote URL, or after advancing to a newer commit).
    lockfile["framework_remote_url"] = origin["framework_remote_url"]
    lockfile["framework_branch"] = origin["framework_branch"]
    lockfile["framework_commit"] = origin["framework_commit"]

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
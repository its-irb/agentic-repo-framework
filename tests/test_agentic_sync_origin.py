"""Traceability tests for ``bin/agentic-sync.py`` origin registration.

These tests verify that ``--apply`` records the framework origin (canonical
remote URL, branch and full commit SHA) in the target's ``.agentic.lock.json``
on every successful sync, that the canonical URL is resolved via
``git ls-remote`` (following GitHub's ``warning: redirecting to`` messages so a
transferred repo records the new location), that the SSH and HTTPS remote
formats are supported, that a failed apply never registers a new commit, and
that an unreliable framework git state or an unresolvable canonical URL halts
the sync with a clear error before touching the target.

They build a synthetic framework git repository under ``tmp_path`` so the
tests can advance commits, change the origin URL and break the git state
without touching the real framework repository. ``subprocess.run`` is
monkeypatched for the ``git ls-remote`` call so the suite is fully offline
and deterministic; the live network behavior of the resolver is exercised
manually.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "agentic-sync.py"


def _load_agentic_sync():
    """Import ``bin/agentic-sync.py`` as a module (its name has a hyphen)."""
    spec = importlib.util.spec_from_file_location("agentic_sync", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def agentic_sync():
    return _load_agentic_sync()


def _git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stripped stdout (fails the test on error)."""
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def _git_init(path: Path) -> None:
    """Initialize a minimal git repo with a test identity."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def _make_framework(
    tmp_path: Path,
    *,
    origin_url: str | None = "git@github.com:test/framework.git",
    commit: bool = True,
    detached: bool = False,
) -> Path:
    """Build a synthetic framework git repo with a minimal manifest and skills.

    The repo contains one core skill (``sample``) with wrappers for every
    managed skill root plus ``docs/documentation-methodology.md``, so
    ``apply_plan`` has real managed files to install.

    Parameters control the git state to exercise the traceability edges:
      - ``origin_url=None``: no ``origin`` remote is configured.
      - ``commit=False``: files are written but nothing is committed (empty repo).
      - ``detached=True``: HEAD is detached at the initial commit.
    """
    fw = tmp_path / "framework"
    fw.mkdir()
    _git_init(fw)
    if origin_url is not None:
        subprocess.run(["git", "remote", "add", "origin", origin_url], cwd=fw, check=True)

    (fw / ".agentic-framework.json").write_text(
        json.dumps(
            {
                "framework_version": "0.1.0",
                "managed_files": ["docs/documentation-methodology.md"],
                "managed_skill_roots": [
                    ".agentic/skills",
                    ".claude/skills",
                    ".opencode/skills",
                ],
            }
        ),
        encoding="utf-8",
    )

    (fw / "docs").mkdir()
    (fw / "docs" / "documentation-methodology.md").write_text("# Methodology\n", encoding="utf-8")

    for skill_root in (
        ".agentic/skills/sample",
        ".claude/skills/sample",
        ".opencode/skills/sample",
    ):
        skill_dir = fw / skill_root
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Sample skill\n", encoding="utf-8")

    if commit:
        subprocess.run(["git", "add", "-A"], cwd=fw, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=fw, check=True)
        if detached:
            sha = _git(["rev-parse", "HEAD"], fw)
            subprocess.run(["git", "checkout", "-q", "--detach", sha], cwd=fw, check=True)

    return fw


def _make_target(tmp_path: Path) -> Path:
    target = tmp_path / "consumer"
    target.mkdir()
    _git_init(target)
    return target


def _load_manifest(fw: Path) -> dict:
    return json.loads((fw / ".agentic-framework.json").read_text(encoding="utf-8"))


class _FakeCompleted:
    """Mimics subprocess.CompletedProcess for the git ls-remote stub."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_lsremote(monkeypatch, agentic_sync, *, returncode: int = 0,
                    stdout: str = "", stderr: str = "") -> None:
    """Monkeypatch ``subprocess.run`` as used by ``_run_git_lsremote``.

    Only the ``git ls-remote`` invocation is stubbed: the fake inspects the
    command argv and only responds to ``ls-remote``; any other git call is
    delegated to the real ``subprocess.run`` so the synthetic framework's
    branch/commit/remote introspection keeps working.
    """
    real_run = subprocess.run

    def _fake(args, *rest, **kw):
        if args[:3] == ["git", "ls-remote", *args[2:3]] or (len(args) >= 2 and args[0] == "git" and args[1] == "ls-remote"):
            return _FakeCompleted(returncode, stdout, stderr)
        return real_run(args, *rest, **kw)

    monkeypatch.setattr(agentic_sync.subprocess, "run", _fake)


# ---------------------------------------------------------------------------
# _parse_github_remote unit tests (pure, no network, no monkeypatch)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("git@github.com:org/repo.git", ("org", "repo")),
        ("git@github.com:org/repo", ("org", "repo")),
        ("ssh://git@github.com/org/repo.git", ("org", "repo")),
        ("ssh://git@github.com/org/repo", ("org", "repo")),
        ("https://github.com/org/repo.git", ("org", "repo")),
        ("https://github.com/org/repo", ("org", "repo")),
        ("https://user:token@github.com/org/repo.git", ("org", "repo")),
    ],
)
def test_parse_github_remote_supported_formats(agentic_sync, url, expected):
    """SSH scp-like, SSH explicit and HTTPS remotes all parse to (owner, repo)."""
    assert agentic_sync._parse_github_remote(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/org/repo.git",
        "git@gitlab.com:org/repo.git",
        "https://github.com/org/repo/sub.git",
        "file:///path/to/repo",
        "git@github.com:org",
        "",
    ],
)
def test_parse_github_remote_rejects_unsupported(agentic_sync, url):
    """Non-GitHub hosts and malformed URLs yield None (no fabricated pair)."""
    assert agentic_sync._parse_github_remote(url) is None


# ---------------------------------------------------------------------------
# _ssh_to_https unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("git@github.com:org/repo.git", "https://github.com/org/repo.git"),
        ("git@github.com:org/repo", "https://github.com/org/repo.git"),
        ("ssh://git@github.com/org/repo.git", "https://github.com/org/repo.git"),
        ("ssh://git@github.com/org/repo", "https://github.com/org/repo.git"),
        ("https://github.com/org/repo.git", None),
        ("https://gitlab.com/org/repo.git", None),
        ("file:///path/to/repo", None),
    ],
)
def test_ssh_to_https(agentic_sync, url, expected):
    """SSH GitHub URLs convert to HTTPS; non-SSH/non-GitHub yield None."""
    assert agentic_sync._ssh_to_https(url) == expected


# ---------------------------------------------------------------------------
# _normalize_github_https unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/org/repo.git", "https://github.com/org/repo.git"),
        ("https://github.com/org/repo", "https://github.com/org/repo.git"),
        ("https://github.com/org/repo.git/", "https://github.com/org/repo.git"),
        ("https://github.com/org/repo/", "https://github.com/org/repo.git"),
    ],
)
def test_normalize_github_https_accepts_with_without_git_and_slash(agentic_sync, url, expected):
    """.git and trailing slash are optional; output is always normalized."""
    assert agentic_sync._normalize_github_https(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/org/repo.git",        # wrong scheme
        "https://gitlab.com/org/repo.git",       # wrong host
        "https://github.com/org",                # missing repo
        "https://github.com/",                   # missing segments
        "ssh://git@github.com/org/repo.git",     # SSH, not HTTPS
        "not a url",
    ],
)
def test_normalize_github_https_rejects_invalid(agentic_sync, url):
    """Non-HTTPS, non-github.com, or malformed URLs raise ValueError."""
    with pytest.raises(ValueError):
        agentic_sync._normalize_github_https(url)


# ---------------------------------------------------------------------------
# _resolve_github_canonical behavior (monkeypatched subprocess.run, no network)
# ---------------------------------------------------------------------------


def test_resolve_canonical_https_no_redirect_keeps_url(agentic_sync, monkeypatch):
    """HTTPS remote, no redirect warning, rc=0 -> URL canónica = la consultada."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr="")
    assert agentic_sync._resolve_github_canonical("https://github.com/org/repo.git") \
        == "https://github.com/org/repo.git"


def test_resolve_canonical_ssh_normalized_to_https(agentic_sync, monkeypatch):
    """SSH remote is converted to HTTPS before the git ls-remote call."""
    captured: dict = {}

    real_run = subprocess.run

    def _fake(args, *rest, **kw):
        if len(args) >= 2 and args[0] == "git" and args[1] == "ls-remote":
            captured["url"] = args[2]
            return _FakeCompleted(0, "abc123\tHEAD\n", "")
        return real_run(args, *rest, **kw)

    monkeypatch.setattr(agentic_sync.subprocess, "run", _fake)

    result = agentic_sync._resolve_github_canonical("git@github.com:org/repo.git")
    assert result == "https://github.com/org/repo.git"
    # The query URL passed to git ls-remote was the HTTPS form.
    assert captured["url"] == "https://github.com/org/repo.git"


def test_resolve_canonical_follows_redirect_warning(agentic_sync, monkeypatch):
    """A 'warning: redirecting to' line records the NEW canonical URL."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr="warning: redirecting to https://github.com/new-org/repo.git/\n")
    assert agentic_sync._resolve_github_canonical("https://github.com/old-org/repo.git") \
        == "https://github.com/new-org/repo.git"


def test_resolve_canonical_redirect_without_git_suffix(agentic_sync, monkeypatch):
    """Redirect URL without .git is normalized to include .git."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr="warning: redirecting to https://github.com/new-org/repo/\n")
    assert agentic_sync._resolve_github_canonical("https://github.com/old-org/repo.git") \
        == "https://github.com/new-org/repo.git"


def test_resolve_canonical_uses_last_redirect_when_multiple(agentic_sync, monkeypatch):
    """Multiple redirects: the last one is the final destination."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr=(
                        "warning: redirecting to https://github.com/mid/repo.git/\n"
                        "warning: redirecting to https://github.com/final/repo.git/\n"
                    ))
    assert agentic_sync._resolve_github_canonical("https://github.com/old/repo.git") \
        == "https://github.com/final/repo.git"


def test_resolve_canonical_lsremote_failure_aborts(agentic_sync, monkeypatch):
    """git ls-remote non-zero exit -> ValueError, no fabricated URL."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=128,
                    stdout="",
                    stderr="fatal: repository 'https://github.com/org/repo.git' not found\n")
    with pytest.raises(ValueError) as exc:
        agentic_sync._resolve_github_canonical("https://github.com/org/repo.git")
    assert "git ls-remote failed" in str(exc.value)
    assert "not found" in str(exc.value)


def test_resolve_canonical_redirect_to_non_github_aborts(agentic_sync, monkeypatch):
    """Redirect to a non-github.com host -> ValueError."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr="warning: redirecting to https://example.com/org/repo.git/\n")
    with pytest.raises(ValueError) as exc:
        agentic_sync._resolve_github_canonical("https://github.com/org/repo.git")
    assert "github.com" in str(exc.value) or "HTTPS" in str(exc.value)


def test_resolve_canonical_malformed_redirect_warning_aborts(agentic_sync, monkeypatch):
    """A redirect warning whose captured URL cannot be normalized -> ValueError.

    The regex extracts the token after 'redirecting to'; the validator then
    rejects it. A non-github.com host exercises this path.
    """
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr="warning: redirecting to https://gitlab.com/org/repo.git/\n")
    with pytest.raises(ValueError):
        agentic_sync._resolve_github_canonical("https://github.com/org/repo.git")


def test_resolve_canonical_non_github_remote_aborts(agentic_sync, monkeypatch):
    """A non-GitHub origin URL is rejected before any git ls-remote call."""
    called: list[str] = []

    real_run = subprocess.run

    def _fake(args, *rest, **kw):
        if len(args) >= 2 and args[0] == "git" and args[1] == "ls-remote":
            called.append("ls-remote")
            return _FakeCompleted(0, "abc\tHEAD\n", "")
        return real_run(args, *rest, **kw)

    monkeypatch.setattr(agentic_sync.subprocess, "run", _fake)

    with pytest.raises(ValueError) as exc:
        agentic_sync._resolve_github_canonical("https://gitlab.com/org/repo.git")
    assert "github" in str(exc.value).lower() or "supported" in str(exc.value).lower()
    assert called == []  # no remote call attempted


def test_resolve_canonical_passes_lc_all_c_and_no_prompt(agentic_sync, monkeypatch):
    """The git ls-remote subprocess runs with LC_ALL=C and GIT_TERMINAL_PROMPT=0."""
    captured: dict = {}

    real_run = subprocess.run

    def _fake(args, *rest, **kw):
        if len(args) >= 2 and args[0] == "git" and args[1] == "ls-remote":
            captured["env"] = kw.get("env", {})
            return _FakeCompleted(0, "abc\tHEAD\n", "")
        return real_run(args, *rest, **kw)

    monkeypatch.setattr(agentic_sync.subprocess, "run", _fake)

    agentic_sync._resolve_github_canonical("https://github.com/org/repo.git")
    env = captured["env"]
    assert env.get("LC_ALL") == "C"
    assert env.get("GIT_TERMINAL_PROMPT") == "0"


def test_resolve_canonical_does_not_use_quiet(agentic_sync, monkeypatch):
    """The git ls-remote command must NOT pass --quiet."""
    captured: dict = {}

    real_run = subprocess.run

    def _fake(args, *rest, **kw):
        if len(args) >= 2 and args[0] == "git" and args[1] == "ls-remote":
            captured["args"] = args
            return _FakeCompleted(0, "abc\tHEAD\n", "")
        return real_run(args, *rest, **kw)

    monkeypatch.setattr(agentic_sync.subprocess, "run", _fake)

    agentic_sync._resolve_github_canonical("https://github.com/org/repo.git")
    assert "--quiet" not in captured["args"]


# ---------------------------------------------------------------------------
# apply_plan integration (synthetic framework, ls-remote monkeypatched)
# ---------------------------------------------------------------------------


def _patch_ok_lsremote(monkeypatch, agentic_sync, canonical: str = "https://github.com/test/framework.git"):
    """Stub ls-remote to succeed with no redirect (canonical = queried URL)."""
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0,
                    stdout="abc123\tHEAD\n",
                    stderr="")


def test_apply_writes_origin_info_after_successful_apply(agentic_sync, tmp_path, monkeypatch):
    """The three origin keys are written after a successful apply."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)
    _patch_ok_lsremote(monkeypatch, agentic_sync)

    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0

    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    assert lock["framework_remote_url"] == "https://github.com/test/framework.git"
    assert lock["framework_branch"] == _git(["symbolic-ref", "--short", "HEAD"], fw)
    assert lock["framework_commit"] == _git(["rev-parse", "HEAD"], fw)

    commit = lock["framework_commit"]
    assert len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit)


def test_old_lockfile_without_origin_is_updated(agentic_sync, tmp_path, monkeypatch):
    """A pre-existing lockfile with no origin keys gets them added correctly."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)
    _patch_ok_lsremote(monkeypatch, agentic_sync)

    documentation = {
        "last_reviewed_commit": "abc123",
        "last_reviewed_at": "2026-01-01T00:00:00Z",
    }
    old_lock = {
        "framework_version": "0.0.0",
        "installed_at": "2020-01-01T00:00:00+00:00",
        "source": "/old/path",
        "managed_core_skills": [],
        "managed_files": {},
        "documentation": documentation,
    }
    (target / ".agentic.lock.json").write_text(
        json.dumps(old_lock, indent=2) + "\n", encoding="utf-8"
    )

    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0

    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    assert lock["framework_remote_url"] == "https://github.com/test/framework.git"
    assert lock["framework_branch"] == _git(["symbolic-ref", "--short", "HEAD"], fw)
    assert lock["framework_commit"] == _git(["rev-parse", "HEAD"], fw)
    assert lock["documentation"] == documentation
    assert lock["framework_version"] == "0.1.0"


def test_second_sync_replaces_commit_and_canonical_url(agentic_sync, tmp_path, monkeypatch):
    """A second sync replaces the previous commit and the canonical URL.

    Models a transfer: the locally configured 'origin' URL is UNCHANGED
    (still the old one), but git ls-remote now emits a redirect to the new
    location. The lock must record the new canonical URL and the new commit.
    """
    fw = _make_framework(tmp_path, origin_url="git@github.com:old-org/framework.git")
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)

    # First apply: old location, no redirect.
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0, stdout="abc\tHEAD\n", stderr="")
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
    lock1 = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    c1 = lock1["framework_commit"]
    assert lock1["framework_remote_url"] == "https://github.com/old-org/framework.git"

    # Advance the framework to a new commit C2.
    (fw / "docs" / "documentation-methodology.md").write_text(
        "# Methodology v2\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=fw, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=fw, check=True)
    c2 = _git(["rev-parse", "HEAD"], fw)
    assert c2 != c1

    # Second apply: git ls-remote now redirects old-org -> new-org (transfer).
    # The local origin URL is STILL old-org; only git's redirect observes it.
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=0, stdout="abc\tHEAD\n",
                    stderr="warning: redirecting to https://github.com/new-org/framework.git/\n")
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
    lock2 = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))

    assert lock2["framework_commit"] == c2
    assert lock2["framework_commit"] != c1
    assert lock2["framework_remote_url"] == "https://github.com/new-org/framework.git"
    assert lock2["framework_branch"] == _git(["symbolic-ref", "--short", "HEAD"], fw)

    assert (
        (target / "docs" / "documentation-methodology.md").read_text(encoding="utf-8")
        == "# Methodology v2\n"
    )


def test_apply_failure_does_not_register_new_commit(agentic_sync, tmp_path, monkeypatch):
    """A mid-apply failure must not register the new commit or URL."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)
    _patch_ok_lsremote(monkeypatch, agentic_sync)

    old_commit = "0" * 40
    old_url = "https://github.com/old/framework.git"
    old_lock = {
        "framework_version": "0.0.0",
        "installed_at": "2020-01-01T00:00:00+00:00",
        "source": "/old",
        "managed_core_skills": [],
        "managed_files": {},
        "framework_remote_url": old_url,
        "framework_branch": "old-branch",
        "framework_commit": old_commit,
        "documentation": {"last_reviewed_commit": "x", "last_reviewed_at": "2026-01-01T00:00:00Z"},
    }
    lockfile_path = target / ".agentic.lock.json"
    lockfile_path.write_text(json.dumps(old_lock, indent=2) + "\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("simulated mid-apply failure")

    monkeypatch.setattr(agentic_sync.shutil, "copy2", boom)

    with pytest.raises(OSError):
        agentic_sync.apply_plan(fw, target, manifest, force=False)

    lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
    assert lock["framework_commit"] == old_commit
    assert lock["framework_remote_url"] == old_url
    assert lock["framework_branch"] == "old-branch"
    assert not (target / ".agentic.lock.json.tmp").exists()


# ---------------------------------------------------------------------------
# resolve_framework_origin failure modes (no target touched)
# ---------------------------------------------------------------------------


def test_resolve_origin_fails_without_origin_remote(agentic_sync, tmp_path):
    """Missing 'origin' remote: clear ValueError, no fabricated URL."""
    fw = _make_framework(tmp_path, origin_url=None)
    with pytest.raises(ValueError) as exc:
        agentic_sync.resolve_framework_origin(fw)
    msg = str(exc.value).lower()
    assert "origin" in msg or "remote" in msg
    assert str(fw) in str(exc.value)


def test_resolve_origin_fails_on_detached_head(agentic_sync, tmp_path):
    """Detached HEAD: clear ValueError, no fabricated branch."""
    fw = _make_framework(tmp_path, detached=True)
    with pytest.raises(ValueError) as exc:
        agentic_sync.resolve_framework_origin(fw)
    msg = str(exc.value).lower()
    assert "branch" in msg
    assert str(fw) in str(exc.value)


def test_resolve_origin_fails_without_commits(agentic_sync, tmp_path):
    """Empty repo (no commits): clear ValueError, no fabricated commit."""
    fw = _make_framework(tmp_path, commit=False)
    with pytest.raises(ValueError) as exc:
        agentic_sync.resolve_framework_origin(fw)
    msg = str(exc.value).lower()
    assert "commit" in msg
    assert str(fw) in str(exc.value)


def test_resolve_origin_fails_on_non_github_remote(agentic_sync, tmp_path):
    """A non-GitHub origin URL is rejected: no fabricated canonical URL."""
    fw = _make_framework(tmp_path, origin_url="https://gitlab.com/org/repo.git")
    with pytest.raises(ValueError) as exc:
        agentic_sync.resolve_framework_origin(fw)
    msg = str(exc.value).lower()
    assert "github" in msg or "supported" in msg


def test_resolve_origin_fails_when_lsremote_fails(agentic_sync, tmp_path, monkeypatch):
    """git ls-remote failure propagates as ValueError, no fallback."""
    fw = _make_framework(tmp_path)
    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=128, stdout="",
                    stderr="fatal: repository not found\n")
    with pytest.raises(ValueError) as exc:
        agentic_sync.resolve_framework_origin(fw)
    assert "git ls-remote failed" in str(exc.value)


def test_apply_halts_on_lsremote_failure_without_touching_target(
    agentic_sync, tmp_path, monkeypatch
):
    """An ls-remote failure halts apply before any change to the target."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)

    old_commit = "1" * 40
    old_lock = {
        "framework_version": "0.0.0",
        "installed_at": "2020-01-01T00:00:00+00:00",
        "source": "/old",
        "managed_core_skills": [],
        "managed_files": {},
        "framework_remote_url": "https://github.com/old/framework.git",
        "framework_branch": "old-branch",
        "framework_commit": old_commit,
    }
    lockfile_path = target / ".agentic.lock.json"
    lockfile_path.write_text(json.dumps(old_lock, indent=2) + "\n", encoding="utf-8")

    _patch_lsremote(monkeypatch, agentic_sync,
                    returncode=128, stdout="",
                    stderr="fatal: repository not found\n")

    with pytest.raises(ValueError):
        agentic_sync.apply_plan(fw, target, manifest, force=False)

    lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
    assert lock["framework_commit"] == old_commit
    assert lock["framework_remote_url"] == "https://github.com/old/framework.git"
    assert lock["framework_branch"] == "old-branch"
    assert not (target / ".agentic" / "skills" / "sample" / "SKILL.md").exists()
    assert not (target / ".agentic.lock.json.tmp").exists()


def test_apply_halts_on_detached_head_without_touching_target(agentic_sync, tmp_path, monkeypatch):
    """Detached HEAD halts apply before any change to the target (origin not
    even reached: no ls-remote call, lockfile untouched)."""
    fw = _make_framework(tmp_path, detached=True)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)

    old_commit = "1" * 40
    old_lock = {
        "framework_version": "0.0.0",
        "managed_files": {},
        "framework_remote_url": "https://github.com/old/framework.git",
        "framework_branch": "old-branch",
        "framework_commit": old_commit,
    }
    lockfile_path = target / ".agentic.lock.json"
    lockfile_path.write_text(json.dumps(old_lock, indent=2) + "\n", encoding="utf-8")

    called: list[str] = []
    real_run = subprocess.run

    def _fake(args, *rest, **kw):
        if len(args) >= 2 and args[0] == "git" and args[1] == "ls-remote":
            called.append("ls-remote")
            return _FakeCompleted(0, "abc\tHEAD\n", "")
        return real_run(args, *rest, **kw)

    monkeypatch.setattr(agentic_sync.subprocess, "run", _fake)

    with pytest.raises(ValueError):
        agentic_sync.apply_plan(fw, target, manifest, force=False)

    lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
    assert lock["framework_commit"] == old_commit
    assert not (target / ".agentic" / "skills" / "sample" / "SKILL.md").exists()
    assert called == []  # ls-remote never reached because HEAD is detached


def test_apply_ssh_and_https_remotes_both_resolve(agentic_sync, tmp_path, monkeypatch):
    """Both SSH and HTTPS configured origins resolve to the same canonical URL."""
    canonical = "https://github.com/test/framework.git"

    origins = (
        "git@github.com:test/framework.git",
        "ssh://git@github.com/test/framework.git",
        "https://github.com/test/framework.git",
        "https://github.com/test/framework",
    )
    for i, origin_url in enumerate(origins):
        base = tmp_path / f"case_{i}"
        base.mkdir()
        fw = _make_framework(base, origin_url=origin_url)
        target = base / "target"
        target.mkdir()
        _git_init(target)
        manifest = _load_manifest(fw)

        _patch_lsremote(monkeypatch, agentic_sync,
                        returncode=0, stdout="abc\tHEAD\n", stderr="")

        assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
        lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
        assert lock["framework_remote_url"] == canonical, origin_url

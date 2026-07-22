"""Traceability tests for ``bin/agentic-sync.py`` origin registration.

These tests verify that ``--apply`` records the framework origin (canonical
remote URL, branch and full commit SHA) in the target's ``.agentic.lock.json``
on every successful sync, that the canonical URL is resolved by following
GitHub redirects (so a transferred repo records the new location), that the
SSH and HTTPS remote formats are supported, that a failed apply never registers
a new commit, and that an unreliable framework git state or an unresolvable
canonical URL halts the sync with a clear error before touching the target.

They build a synthetic framework git repository under ``tmp_path`` so the
tests can advance commits, change the origin URL and break the git state
without touching the real framework repository. The GitHub canonical resolver
(``_resolve_github_canonical``) is monkeypatched so the suite is fully offline
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


def _patch_resolver(monkeypatch, agentic_sync, canonical_url: str) -> None:
    """Monkeypatch the GitHub canonical resolver to a fixed offline value.

    Makes the suite fully deterministic and offline: ``resolve_framework_origin``
    still exercises parsing + git introspection, but the network step is stubbed.
    """
    monkeypatch.setattr(
        agentic_sync,
        "_resolve_github_canonical",
        lambda owner, repo: canonical_url,
    )


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
        "https://github.com/org/repo/sub.git",   # too many segments
        "file:///path/to/repo",
        "git@github.com:org",                     # missing repo
        "",
    ],
)
def test_parse_github_remote_rejects_unsupported(agentic_sync, url):
    """Non-GitHub hosts and malformed URLs yield None (no fabricated pair)."""
    assert agentic_sync._parse_github_remote(url) is None


# ---------------------------------------------------------------------------
# _resolve_github_canonical behavior (monkeypatched urlopen, no real network)
# ---------------------------------------------------------------------------


class _FakeResp:
    """Minimal context manager mimicking urllib's response object."""

    def __init__(self, final_url: str, status: int = 200):
        self._final_url = final_url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def geturl(self):
        return self._final_url


def _patch_urlopen(monkeypatch, agentic_sync, final_url: str, status: int = 200):
    """Monkeypatch ``urllib.request.urlopen`` as used by the resolver."""

    def _fake(req, timeout=None):
        return _FakeResp(final_url, status)

    monkeypatch.setattr(agentic_sync.urllib.request, "urlopen", _fake)


def test_resolve_canonical_no_redirect_keeps_url(agentic_sync, monkeypatch):
    """A public repo with no transfer: final URL == requested URL."""
    _patch_urlopen(monkeypatch, agentic_sync,
                   "https://github.com/org/repo", status=200)
    assert agentic_sync._resolve_github_canonical("org", "repo") \
        == "https://github.com/org/repo.git"


def test_resolve_canonical_follows_redirect_to_new_location(agentic_sync, monkeypatch):
    """A 301 transfer (old owner -> new owner) records the NEW canonical URL.

    This is the core correction: the locally configured URL stays 'old/repo'
    but GitHub redirects to 'new/repo'; the lock must record 'new/repo'.
    """
    _patch_urlopen(monkeypatch, agentic_sync,
                   "https://github.com/new-org/repo", status=200)
    assert agentic_sync._resolve_github_canonical("old-org", "repo") \
        == "https://github.com/new-org/repo.git"


def test_resolve_canonical_http_error_aborts(agentic_sync, monkeypatch):
    """A 404 (private/inexistent repo) raises ValueError, no fabricated URL."""
    import urllib.error

    def _fake(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(agentic_sync.urllib.request, "urlopen", _fake)
    with pytest.raises(ValueError) as exc:
        agentic_sync._resolve_github_canonical("org", "repo")
    assert "404" in str(exc.value)


def test_resolve_canonical_network_error_aborts(agentic_sync, monkeypatch):
    """A URLError (offline / timeout) raises ValueError, no fabricated URL."""
    import urllib.error

    def _fake(req, timeout=None):
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(agentic_sync.urllib.request, "urlopen", _fake)
    with pytest.raises(ValueError) as exc:
        agentic_sync._resolve_github_canonical("org", "repo")
    assert "network" in str(exc.value).lower() or "getaddrinfo" in str(exc.value)


def test_resolve_canonical_redirect_off_github_aborts(agentic_sync, monkeypatch):
    """A redirect to a non-github.com host is rejected."""
    _patch_urlopen(monkeypatch, agentic_sync,
                   "https://example.com/org/repo", status=200)
    with pytest.raises(ValueError) as exc:
        agentic_sync._resolve_github_canonical("org", "repo")
    assert "github.com" in str(exc.value) or "host" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# apply_plan integration (synthetic framework, resolver monkeypatched)
# ---------------------------------------------------------------------------


def test_apply_writes_origin_info_after_successful_apply(agentic_sync, tmp_path, monkeypatch):
    """The three origin keys are written after a successful apply, matching git."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)
    _patch_resolver(monkeypatch, agentic_sync,
                    "https://github.com/test/framework.git")

    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0

    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    assert lock["framework_remote_url"] == "https://github.com/test/framework.git"
    assert lock["framework_branch"] == _git(["symbolic-ref", "--short", "HEAD"], fw)
    assert lock["framework_commit"] == _git(["rev-parse", "HEAD"], fw)

    # Full 40-char lowercase hex SHA.
    commit = lock["framework_commit"]
    assert len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit)


def test_old_lockfile_without_origin_is_updated(agentic_sync, tmp_path, monkeypatch):
    """A pre-existing lockfile with no origin keys gets them added correctly."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)
    _patch_resolver(monkeypatch, agentic_sync,
                    "https://github.com/test/framework.git")

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

    # Origin keys added from the framework git repo + canonical resolver.
    assert lock["framework_remote_url"] == "https://github.com/test/framework.git"
    assert lock["framework_branch"] == _git(["symbolic-ref", "--short", "HEAD"], fw)
    assert lock["framework_commit"] == _git(["rev-parse", "HEAD"], fw)

    # External documentation key preserved, managed keys refreshed.
    assert lock["documentation"] == documentation
    assert lock["framework_version"] == "0.1.0"


def test_second_sync_replaces_commit_and_canonical_url(agentic_sync, tmp_path, monkeypatch):
    """A second sync replaces the previous commit and the canonical URL.

    This models a transfer: the locally configured 'origin' URL is UNCHANGED
    (still the old one), but GitHub now redirects to a new location. The lock
    must record the new canonical URL and the new commit, replacing the old
    values. This is the case the previous implementation (raw
    `git remote get-url origin`) could not handle.
    """
    fw = _make_framework(tmp_path, origin_url="git@github.com:old-org/framework.git")
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)

    # First apply: old location, no redirect.
    _patch_resolver(monkeypatch, agentic_sync,
                    "https://github.com/old-org/framework.git")
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

    # Second apply: GitHub now redirects old-org -> new-org (transfer).
    # The local origin URL is STILL old-org; only the canonical resolver
    # observes the new location.
    _patch_resolver(monkeypatch, agentic_sync,
                    "https://github.com/new-org/framework.git")
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
    lock2 = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))

    assert lock2["framework_commit"] == c2
    assert lock2["framework_commit"] != c1
    assert lock2["framework_remote_url"] == "https://github.com/new-org/framework.git"
    assert lock2["framework_branch"] == _git(["symbolic-ref", "--short", "HEAD"], fw)

    # The updated managed file was actually installed.
    assert (
        (target / "docs" / "documentation-methodology.md").read_text(encoding="utf-8")
        == "# Methodology v2\n"
    )


def test_apply_failure_does_not_register_new_commit(agentic_sync, tmp_path, monkeypatch):
    """A mid-apply failure must not register the new framework commit or URL."""
    fw = _make_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = _load_manifest(fw)
    _patch_resolver(monkeypatch, agentic_sync,
                    "https://github.com/test/framework.git")

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

    # Simulate a failure during file installation: shutil.copy2 raises. The
    # origin was already resolved successfully, but the lockfile write (the last
    # step) is never reached, so the stored commit/URL must remain the old ones.
    def boom(*args, **kwargs):
        raise OSError("simulated mid-apply failure")

    monkeypatch.setattr(agentic_sync.shutil, "copy2", boom)

    with pytest.raises(OSError):
        agentic_sync.apply_plan(fw, target, manifest, force=False)

    lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
    assert lock["framework_commit"] == old_commit
    assert lock["framework_remote_url"] == old_url
    assert lock["framework_branch"] == "old-branch"
    # No partial lockfile left behind.
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


def test_resolve_origin_fails_when_canonical_resolution_fails(agentic_sync, tmp_path, monkeypatch):
    """A resolver failure (network/HTTP) propagates as ValueError, no fallback."""
    fw = _make_framework(tmp_path)

    def _boom(owner, repo):
        raise ValueError("network error")

    monkeypatch.setattr(agentic_sync, "_resolve_github_canonical", _boom)
    with pytest.raises(ValueError) as exc:
        agentic_sync.resolve_framework_origin(fw)
    assert "network" in str(exc.value).lower()


def test_apply_halts_on_unresolvable_canonical_url_without_touching_target(
    agentic_sync, tmp_path, monkeypatch
):
    """An unresolvable canonical URL halts apply before any change to the target."""
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

    def _boom(owner, repo):
        raise ValueError("HTTP 404 resolving org/repo")

    monkeypatch.setattr(agentic_sync, "_resolve_github_canonical", _boom)

    with pytest.raises(ValueError):
        agentic_sync.apply_plan(fw, target, manifest, force=False)

    # Lockfile unchanged: the new commit/URL was NOT registered.
    lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
    assert lock["framework_commit"] == old_commit
    assert lock["framework_remote_url"] == "https://github.com/old/framework.git"
    assert lock["framework_branch"] == "old-branch"

    # No managed files installed: apply halted before the file loop.
    assert not (target / ".agentic" / "skills" / "sample" / "SKILL.md").exists()
    # No partial lockfile left behind.
    assert not (target / ".agentic.lock.json.tmp").exists()


def test_apply_halts_on_detached_head_without_touching_target(agentic_sync, tmp_path, monkeypatch):
    """Detached HEAD halts apply before any change to the target (origin not
    even reached: no network call, lockfile untouched)."""
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

    # Resolver must NOT be called (detached HEAD fails first). If it were, this
    # marker would surface the bug.
    def _must_not_be_called(owner, repo):
        raise AssertionError("resolver called despite detached HEAD")

    monkeypatch.setattr(agentic_sync, "_resolve_github_canonical", _must_not_be_called)

    with pytest.raises(ValueError):
        agentic_sync.apply_plan(fw, target, manifest, force=False)

    lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
    assert lock["framework_commit"] == old_commit
    assert not (target / ".agentic" / "skills" / "sample" / "SKILL.md").exists()


def test_apply_ssh_and_https_remotes_both_resolve(agentic_sync, tmp_path, monkeypatch):
    """Both SSH and HTTPS configured origins resolve to the same canonical URL."""
    canonical = "https://github.com/test/framework.git"
    _patch_resolver(monkeypatch, agentic_sync, canonical)

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

        assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
        lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
        assert lock["framework_remote_url"] == canonical, origin_url

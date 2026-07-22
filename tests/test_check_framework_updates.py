"""Tests for ``.agentic/tools/check-framework-updates.py``.

These tests are fully offline: ``run_lsremote`` is monkeypatched so no real
``git ls-remote`` (and no network) is needed. They cover the eight documented
states, full-SHA comparison (no abbreviated fallback), the guarantee that the
tool never modifies the target repository, and that ``agentic-sync.py``
distributes the tool and the OpenCode plugin to consumer repositories.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_PATH = REPO_ROOT / ".agentic" / "tools" / "check-framework-updates.py"
SCRIPT_PATH = REPO_ROOT / "bin" / "agentic-sync.py"

SHA_A = "a" * 40
SHA_B = "b" * 40
REQUIRED_FIELDS_EXPECTED = {
    "framework_remote_url", "framework_branch", "framework_commit",
}


def _load_tool():
    """Import the check tool as a module."""
    spec = importlib.util.spec_from_file_location("agentic_check_updates", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_agentic_sync():
    spec = importlib.util.spec_from_file_location("agentic_sync", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def _make_target(tmp_path: Path) -> Path:
    target = tmp_path / "consumer"
    target.mkdir()
    _git_init(target)
    return target


def _write_lock(root: Path, *, url="https://github.com/org/framework.git",
                branch="main", commit=SHA_A, extra=None) -> None:
    data = {
        "framework_remote_url": url,
        "framework_branch": branch,
        "framework_commit": commit,
    }
    if extra:
        data.update(extra)
    (root / ".agentic.lock.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def _commit_all(root: Path, msg="init") -> None:
    """Stage and commit everything so the working tree is clean (tracked)."""
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=root, check=True)


def _make_local_remote(tmp_path: Path, branch="main") -> tuple[Path, str]:
    """Create a real local git repo usable as an offline ``ls-remote`` target.

    Returns ``(remote_path, head_sha)``. The repo has one commit on ``branch``;
    its HEAD SHA is a real 40-char hex, so the tool's full-SHA comparison and
    the CLI subprocess can exercise the real ``git ls-remote`` path without any
    network access.
    """
    remote = tmp_path / "remote"
    remote.mkdir()
    _git_init(remote)
    (remote / "file.txt").write_text("x", encoding="utf-8")
    _commit_all(remote, "remote init")
    subprocess.run(["git", "branch", "-M", branch], cwd=remote, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=remote,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return remote, sha


@pytest.fixture()
def tool():
    return _load_tool()


@pytest.fixture()
def agentic_sync():
    return _load_agentic_sync()


def _patch_lsremote(monkeypatch, tool, *, returncode=0, stdout="", stderr=""):
    monkeypatch.setattr(
        tool, "run_lsremote",
        lambda url, branch: (returncode, stdout, stderr),
    )


# ---------------------------------------------------------------------------
# The eight documented states
# ---------------------------------------------------------------------------


def test_up_to_date(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0
    assert r["status"] == "UP_TO_DATE"
    assert r["installed_commit"] == SHA_A
    assert r["remote_commit"] == SHA_A


def test_update_available(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_B}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 1
    assert r["status"] == "UPDATE_AVAILABLE"
    assert r["installed_commit"] == SHA_A
    assert r["remote_commit"] == SHA_B
    assert r["branch"] == "main"
    assert r["url"] == "https://github.com/org/framework.git"


def test_framework_source_exposed_when_present(tool, tmp_path, monkeypatch):
    """When lock has a non-empty string 'source', it surfaces as framework_source."""
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A, extra={"source": "/home/david/fw"})
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0
    assert r["framework_source"] == "/home/david/fw"


def test_framework_source_absent_when_not_a_string(tool, tmp_path, monkeypatch):
    """A non-string or empty source is ignored (framework_source not added)."""
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A, extra={"source": 12345})
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0
    assert "framework_source" not in r


def test_framework_source_absent_when_empty(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A, extra={"source": ""})
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0
    assert "framework_source" not in r


def test_framework_source_exposed_on_update_available(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A, extra={"source": "/fw"})
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_B}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 1
    assert r["framework_source"] == "/fw"


def test_framework_source_exposed_on_lock_incomplete(tool, tmp_path):
    """source is surfaced even when the lock is incomplete (it was read)."""
    target = _make_target(tmp_path)
    (target / ".agentic.lock.json").write_text(
        json.dumps({"documentation": {}, "source": "/fw"}) + "\n",
        encoding="utf-8",
    )
    r = tool.check(target)
    assert r["code"] == 4
    assert r["framework_source"] == "/fw"


def test_source_repo_skipped(tool, tmp_path):
    target = _make_target(tmp_path)
    (target / ".agentic-framework.json").write_text("{}", encoding="utf-8")
    r = tool.check(target)
    assert r["code"] == 2
    assert r["status"] == "SOURCE_REPO_SKIPPED"


def test_lock_missing(tool, tmp_path):
    target = _make_target(tmp_path)
    # No .agentic.lock.json created at all.
    assert not (target / ".agentic.lock.json").exists()
    r = tool.check(target)
    assert r["code"] == 3
    assert r["status"] == "LOCK_MISSING"
    # A missing lock must NOT surface framework_source (no lock was read).
    assert "framework_source" not in r


def test_lock_present_but_empty_object_is_incomplete(tool, tmp_path):
    """An existing {} lock is present-but-incomplete, NOT missing."""
    target = _make_target(tmp_path)
    (target / ".agentic.lock.json").write_text("{}\n", encoding="utf-8")
    r = tool.check(target)
    assert r["code"] == 4
    assert r["status"] == "LOCK_INCOMPLETE"
    assert set(r["missing_fields"]) == set(REQUIRED_FIELDS_EXPECTED)


def test_lock_incomplete_missing_traceability_fields(tool, tmp_path):
    target = _make_target(tmp_path)
    # Old lock: only documentation baseline, no framework_* fields.
    (target / ".agentic.lock.json").write_text(
        json.dumps({"documentation": {"last_reviewed_commit": "x",
                                      "last_reviewed_at": "2026-01-01T00:00:00Z"}}) + "\n",
        encoding="utf-8",
    )
    r = tool.check(target)
    assert r["code"] == 4
    assert r["status"] == "LOCK_INCOMPLETE"
    assert set(r["missing_fields"]) == REQUIRED_FIELDS_EXPECTED


def test_lock_incomplete_missing_single_field(tool, tmp_path):
    """A lock missing just one of the required fields is incomplete."""
    target = _make_target(tmp_path)
    (target / ".agentic.lock.json").write_text(
        json.dumps({
            "framework_remote_url": "https://github.com/org/fw.git",
            "framework_branch": "main",
            # framework_commit missing
        }) + "\n",
        encoding="utf-8",
    )
    r = tool.check(target)
    assert r["code"] == 4
    assert r["status"] == "LOCK_INCOMPLETE"
    assert r["missing_fields"] == ["framework_commit"]


def test_lock_invalid_bad_json(tool, tmp_path):
    target = _make_target(tmp_path)
    (target / ".agentic.lock.json").write_text("{ broken json", encoding="utf-8")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"


def test_lock_invalid_not_an_object(tool, tmp_path):
    target = _make_target(tmp_path)
    (target / ".agentic.lock.json").write_text('["not", "an", "object"]', encoding="utf-8")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"


def test_lock_invalid_abbreviated_commit(tool, tmp_path, monkeypatch):
    """An abbreviated (non-40-char) commit must NOT be accepted: no fallback."""
    target = _make_target(tmp_path)
    _write_lock(target, commit="abc1237")  # 7 chars
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"


# ---------------------------------------------------------------------------
# Type validation of framework_commit / url / branch (LOCK_INVALID, no throw)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("commit_value", [12345, 12.5, ["aaa"], {"x": 1}, True, None])
def test_commit_non_string_is_lock_invalid(tool, tmp_path, monkeypatch, commit_value):
    """A non-string framework_commit must yield LOCK_INVALID without exception."""
    target = _make_target(tmp_path)
    (target / ".agentic.lock.json").write_text(
        json.dumps({
            "framework_remote_url": "https://github.com/org/fw.git",
            "framework_branch": "main",
            "framework_commit": commit_value,
        }) + "\n",
        encoding="utf-8",
    )
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"
    assert "framework_commit" in r["message"]
    assert "string" in r["message"]


@pytest.mark.parametrize("field", ["framework_remote_url", "framework_branch"])
def test_url_or_branch_non_string_is_lock_invalid(tool, tmp_path, monkeypatch, field):
    target = _make_target(tmp_path)
    data = {
        "framework_remote_url": "https://github.com/org/fw.git",
        "framework_branch": "main",
        "framework_commit": SHA_A,
    }
    data[field] = 42
    (target / ".agentic.lock.json").write_text(
        json.dumps(data) + "\n", encoding="utf-8",
    )
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"
    assert field in r["message"]
    assert "string" in r["message"]


@pytest.mark.parametrize("field", ["framework_remote_url", "framework_branch"])
def test_url_or_branch_empty_string_is_lock_invalid(tool, tmp_path, monkeypatch, field):
    target = _make_target(tmp_path)
    data = {
        "framework_remote_url": "https://github.com/org/fw.git",
        "framework_branch": "main",
        "framework_commit": SHA_A,
    }
    data[field] = ""
    (target / ".agentic.lock.json").write_text(
        json.dumps(data) + "\n", encoding="utf-8",
    )
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"
    assert field in r["message"]
    assert "empty" in r["message"]


# ---------------------------------------------------------------------------
# Whitespace-only strings are treated as empty (LOCK_INVALID / source ignored)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["framework_remote_url", "framework_branch"])
def test_url_or_branch_whitespace_only_is_lock_invalid(tool, tmp_path, monkeypatch, field):
    """A string of only spaces must NOT pass validation."""
    target = _make_target(tmp_path)
    data = {
        "framework_remote_url": "https://github.com/org/fw.git",
        "framework_branch": "main",
        "framework_commit": SHA_A,
    }
    data[field] = "   "
    (target / ".agentic.lock.json").write_text(
        json.dumps(data) + "\n", encoding="utf-8",
    )
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"
    assert field in r["message"]
    assert "empty" in r["message"] or "whitespace" in r["message"]


def test_commit_whitespace_only_is_lock_invalid(tool, tmp_path, monkeypatch):
    """A whitespace-only framework_commit must yield LOCK_INVALID (not reach git)."""
    target = _make_target(tmp_path)
    _write_lock(target, commit="   ")
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 5
    assert r["status"] == "LOCK_INVALID"
    assert "framework_commit" in r["message"]


def test_source_whitespace_only_is_not_exposed(tool, tmp_path, monkeypatch):
    """A whitespace-only source is ignored: framework_source must NOT appear."""
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A, extra={"source": "   "})
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0
    assert "framework_source" not in r


def test_source_with_internal_spaces_is_exposed_verbatim(tool, tmp_path, monkeypatch):
    """A legitimate source path containing spaces is preserved as-is."""
    target = _make_target(tmp_path)
    legit = "/home/david/my projects/agentic-fw"
    _write_lock(target, commit=SHA_A, extra={"source": legit})
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0
    assert r["framework_source"] == legit


def test_git_lsremote_failure(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    _patch_lsremote(monkeypatch, tool, returncode=128, stdout="",
                    stderr="fatal: repository not found\n")
    r = tool.check(target)
    assert r["code"] == 7
    assert r["status"] == "GIT_OR_NETWORK_ERROR"
    assert "not found" in r["reason"]


# ---------------------------------------------------------------------------
# subprocess execution errors (git missing / OSError / timeout)
# ---------------------------------------------------------------------------


def test_git_not_found_is_git_or_network_error(tool, tmp_path, monkeypatch):
    """FileNotFoundError (git not in PATH) -> GIT_OR_NETWORK_ERROR, no traceback.

    Patches subprocess.run (not run_lsremote) so run_lsremote's own except
    clause is exercised end-to-end.
    """
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)

    def _boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory: 'git'")
    monkeypatch.setattr(tool.subprocess, "run", _boom)

    r = tool.check(target)
    assert r["code"] == 7
    assert r["status"] == "GIT_OR_NETWORK_ERROR"
    assert "git" in r["reason"].lower()
    assert "not found" in r["reason"].lower() or "path" in r["reason"].lower()


def test_git_oserror_is_git_or_network_error(tool, tmp_path, monkeypatch):
    """A generic OSError executing git -> GIT_OR_NETWORK_ERROR, no traceback."""
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)

    def _boom(*a, **kw):
        raise OSError("permission denied")
    monkeypatch.setattr(tool.subprocess, "run", _boom)

    r = tool.check(target)
    assert r["code"] == 7
    assert r["status"] == "GIT_OR_NETWORK_ERROR"
    assert "could not execute" in r["reason"].lower() or "oserror" in r["reason"].lower()


def test_git_timeout_is_git_or_network_error(tool, tmp_path, monkeypatch):
    """TimeoutExpired -> GIT_OR_NETWORK_ERROR, no traceback."""
    import subprocess as _subprocess
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)

    def _boom(*a, **kw):
        raise _subprocess.TimeoutExpired(cmd=["git", "ls-remote"], timeout=10)
    monkeypatch.setattr(tool.subprocess, "run", _boom)

    r = tool.check(target)
    assert r["code"] == 7
    assert r["status"] == "GIT_OR_NETWORK_ERROR"
    assert "timed out" in r["reason"].lower()


def test_run_lsremote_directly_converts_file_not_found(tool, monkeypatch):
    """Direct unit test: run_lsremote converts FileNotFoundError to (128,_,msg)."""
    def _boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory: 'git'")
    monkeypatch.setattr(tool.subprocess, "run", _boom)
    rc, out, err = tool.run_lsremote("https://example.org/x.git", "main")
    assert rc == 128
    assert out == ""
    assert "git" in err.lower() and ("not found" in err.lower() or "path" in err.lower())


def test_remote_branch_missing(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    # ls-remote succeeds but returns no matching ref (empty stdout).
    _patch_lsremote(monkeypatch, tool, returncode=0, stdout="", stderr="")
    r = tool.check(target)
    assert r["code"] == 6
    assert r["status"] == "REMOTE_BRANCH_MISSING"


# ---------------------------------------------------------------------------
# Full-SHA comparison (no abbreviated fallback)
# ---------------------------------------------------------------------------


def test_full_sha_equality_is_up_to_date(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    # Remote returns the exact same full SHA (with extra refs lines, ignored).
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n{SHA_B}\trefs/tags/v1\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 0


def test_single_char_difference_is_update(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    installed = "a" * 39 + "f"
    remote = "a" * 39 + "e"
    _write_lock(target, commit=installed)
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{remote}\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 1
    assert r["installed_commit"] == installed
    assert r["remote_commit"] == remote


def test_remote_malformed_sha_is_error(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout="notasha\trefs/heads/main\n", stderr="")
    r = tool.check(target)
    assert r["code"] == 7
    assert r["status"] == "GIT_OR_NETWORK_ERROR"


# ---------------------------------------------------------------------------
# No modification of the repository (read-only guarantee)
# ---------------------------------------------------------------------------


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")
            if ".git" not in p.relative_to(root).parts and p.is_file()}


def test_check_never_modifies_repository(tool, tmp_path, monkeypatch):
    target = _make_target(tmp_path)
    _write_lock(target, commit=SHA_A)
    _commit_all(target)  # lockfile tracked -> working tree clean
    _patch_lsremote(monkeypatch, tool, returncode=0,
                    stdout=f"{SHA_A}\trefs/heads/main\n", stderr="")

    before = _snapshot(target)
    clean_before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True
    ).stdout

    r = tool.check(target)
    assert r["code"] == 0

    after = _snapshot(target)
    clean_after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True
    ).stdout

    assert before == after, "tool created or deleted files"
    assert clean_before == clean_after == "", "tool changed the working tree"


def test_cli_never_modifies_repository(tool, tmp_path):
    """CLI end-to-end (real ``git ls-remote`` against a local remote, offline)."""
    target = _make_target(tmp_path)
    remote, remote_sha = _make_local_remote(tmp_path)
    _write_lock(target, url=str(remote), commit=remote_sha)
    _commit_all(target)

    before = _snapshot(target)
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(target)],
        capture_output=True, text=True,
    )
    after = _snapshot(target)
    clean_after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True
    ).stdout

    assert result.returncode == 0, result.stdout
    assert before == after, "CLI created or deleted files"
    assert clean_after == "", "CLI changed the working tree"
    assert json.loads(result.stdout)["code"] == 0


def test_cli_exit_codes_match_states(tmp_path):
    """Source repo (code 2) needs no network; verifies CLI exit-code mapping."""
    src = tmp_path / "src"
    src.mkdir()
    _git_init(src)
    (src / ".agentic-framework.json").write_text("{}", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(src)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert json.loads(r.stdout)["code"] == 2


# ---------------------------------------------------------------------------
# Distribution via agentic-sync.py
# ---------------------------------------------------------------------------


def test_build_managed_files_includes_tool_and_plugin(agentic_sync):
    fw = agentic_sync.find_framework_root()
    manifest = agentic_sync.load_manifest(fw)
    files = agentic_sync.build_managed_files(fw, manifest)
    assert ".agentic/tools/check-framework-updates.py" in files
    assert ".opencode/plugins/agentic-update-check.js" in files
    # The framework manifest is NOT distributed.
    assert ".agentic-framework.json" not in files


def test_apply_distributes_tool_and_plugin(agentic_sync, tmp_path, monkeypatch):
    fw = agentic_sync.find_framework_root()
    manifest = agentic_sync.load_manifest(fw)
    target = _make_target(tmp_path)

    # Offline: stub the canonical URL resolver (no network).
    monkeypatch.setattr(
        agentic_sync, "_resolve_github_canonical",
        lambda configured_url: "https://github.com/test/agentic-repo-framework.git",
    )

    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0

    tool_dst = target / ".agentic" / "tools" / "check-framework-updates.py"
    plugin_dst = target / ".opencode" / "plugins" / "agentic-update-check.js"
    assert tool_dst.exists()
    assert plugin_dst.exists()

    # Contents match the framework source.
    assert tool_dst.read_text(encoding="utf-8") == TOOL_PATH.read_text(encoding="utf-8")

    # Both are recorded in the target lockfile with hashes.
    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    rel_tool = ".agentic/tools/check-framework-updates.py"
    rel_plugin = ".opencode/plugins/agentic-update-check.js"
    assert rel_tool in lock["managed_files"]
    assert rel_plugin in lock["managed_files"]
    assert lock["managed_files"][rel_tool]["sha256"] == agentic_sync.sha256_file(TOOL_PATH)

    # The framework manifest is not installed into the target.
    assert not (target / ".agentic-framework.json").exists()


# ---------------------------------------------------------------------------
# Distribution: update + controlled removal (no deletion of framework or
# third-party tool/plugin files)
# ---------------------------------------------------------------------------


def _make_synth_framework(tmp_path: Path) -> Path:
    """Build a synthetic framework git repo with tool + plugin + a managed file.

    Mirrors the real manifest shape so apply_plan has real files to install and
    we can mutate the source to exercise UPDATE / removal scenarios offline.
    """
    import subprocess as _sp
    fw = tmp_path / "framework"
    fw.mkdir()
    _sp.run(["git", "init", "-q"], cwd=fw, check=True)
    _sp.run(["git", "config", "user.email", "t@e.com"], cwd=fw, check=True)
    _sp.run(["git", "config", "user.name", "T"], cwd=fw, check=True)
    _sp.run(["git", "remote", "add", "origin",
             "git@github.com:test/framework.git"], cwd=fw, check=True)

    (fw / ".agentic-framework.json").write_text(
        json.dumps({
            "framework_version": "0.1.0",
            "managed_files": [
                "docs/documentation-methodology.md",
                ".agentic/tools/check-framework-updates.py",
                ".opencode/plugins/agentic-update-check.js",
            ],
            "managed_skill_roots": [".agentic/skills", ".claude/skills",
                                    ".opencode/skills"],
        }) + "\n",
        encoding="utf-8",
    )
    (fw / "docs").mkdir()
    (fw / "docs" / "documentation-methodology.md").write_text("# M\n", encoding="utf-8")
    (fw / ".agentic" / "tools").mkdir(parents=True)
    (fw / ".agentic" / "tools" / "check-framework-updates.py").write_text(
        "# tool v1\n", encoding="utf-8",
    )
    (fw / ".opencode" / "plugins").mkdir(parents=True)
    (fw / ".opencode" / "plugins" / "agentic-update-check.js").write_text(
        "// plugin v1\n", encoding="utf-8",
    )
    _sp.run(["git", "add", "-A"], cwd=fw, check=True)
    _sp.run(["git", "commit", "-q", "-m", "init"], cwd=fw, check=True)
    return fw


def _stub_origin(agentic_sync, monkeypatch):
    """Stub the canonical URL resolver so apply is fully offline."""
    monkeypatch.setattr(
        agentic_sync, "_resolve_github_canonical",
        lambda configured_url: "https://github.com/test/framework.git",
    )


def test_apply_updates_tool_and_plugin_on_second_sync(agentic_sync, tmp_path, monkeypatch):
    """Changing the framework source and re-applying UPDATEs both files."""
    import subprocess as _sp
    fw = _make_synth_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = json.loads((fw / ".agentic-framework.json").read_text(encoding="utf-8"))
    _stub_origin(agentic_sync, monkeypatch)

    # First apply: install.
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
    tool_dst = target / ".agentic" / "tools" / "check-framework-updates.py"
    plugin_dst = target / ".opencode" / "plugins" / "agentic-update-check.js"
    assert tool_dst.read_text(encoding="utf-8") == "# tool v1\n"
    assert plugin_dst.read_text(encoding="utf-8") == "// plugin v1\n"

    old_tool_hash = agentic_sync.sha256_file(tool_dst)
    old_plugin_hash = agentic_sync.sha256_file(plugin_dst)

    # Mutate the framework source files (new versions).
    tool_dst  # noqa
    (fw / ".agentic" / "tools" / "check-framework-updates.py").write_text(
        "# tool v2 - updated\n", encoding="utf-8",
    )
    (fw / ".opencode" / "plugins" / "agentic-update-check.js").write_text(
        "// plugin v2 - updated\n", encoding="utf-8",
    )
    _sp.run(["git", "add", "-A"], cwd=fw, check=True)
    _sp.run(["git", "commit", "-q", "-m", "v2"], cwd=fw, check=True)

    # Second apply: the destinations match the locked hash (UPDATE, safe).
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0

    assert tool_dst.read_text(encoding="utf-8") == "# tool v2 - updated\n"
    assert plugin_dst.read_text(encoding="utf-8") == "// plugin v2 - updated\n"

    # The lockfile now records the NEW hashes.
    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    rel_tool = ".agentic/tools/check-framework-updates.py"
    rel_plugin = ".opencode/plugins/agentic-update-check.js"
    assert lock["managed_files"][rel_tool]["sha256"] != old_tool_hash
    assert lock["managed_files"][rel_plugin]["sha256"] != old_plugin_hash
    assert lock["managed_files"][rel_tool]["sha256"] == \
        agentic_sync.sha256_file(fw / rel_tool)
    assert lock["managed_files"][rel_plugin]["sha256"] == \
        agentic_sync.sha256_file(fw / rel_plugin)


def test_removal_from_manifest_does_not_delete_target_file(agentic_sync, tmp_path, monkeypatch):
    """agentic-sync never deletes files retired from the manifest.

    A file removed from managed_files is left as an orphan in the target (it is
    no longer tracked), but sync does NOT delete it. This is intentional so the
    framework never destroys third-party work.
    """
    fw = _make_synth_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = json.loads((fw / ".agentic-framework.json").read_text(encoding="utf-8"))
    _stub_origin(agentic_sync, monkeypatch)

    # Install everything.
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
    tool_dst = target / ".agentic" / "tools" / "check-framework-updates.py"
    assert tool_dst.exists()

    # Retire the tool from the manifest in the framework source.
    manifest["managed_files"] = [
        m for m in manifest["managed_files"]
        if m != ".agentic/tools/check-framework-updates.py"
    ]
    (fw / ".agentic-framework.json").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8",
    )
    import subprocess as _sp
    _sp.run(["git", "add", "-A"], cwd=fw, check=True)
    _sp.run(["git", "commit", "-q", "-m", "retire tool"], cwd=fw, check=True)

    # Re-apply: the tool file must STILL exist in the target (orphaned, not deleted).
    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0
    assert tool_dst.exists(), "sync must not delete retired managed files"

    # And it must no longer be tracked in the lockfile.
    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    assert ".agentic/tools/check-framework-updates.py" not in lock["managed_files"]
    # The plugin is still managed.
    assert ".opencode/plugins/agentic-update-check.js" in lock["managed_files"]


def test_sync_does_not_touch_third_party_tools_or_plugins(agentic_sync, tmp_path, monkeypatch):
    """Files under .agentic/tools/ or .opencode/plugins/ that are NOT framework-
    managed must never be installed, updated, or deleted by sync."""
    fw = _make_synth_framework(tmp_path)
    target = _make_target(tmp_path)
    manifest = json.loads((fw / ".agentic-framework.json").read_text(encoding="utf-8"))
    _stub_origin(agentic_sync, monkeypatch)

    # Pre-existing third-party tool and plugin in the target.
    third_tool = target / ".agentic" / "tools" / "my-own-tool.py"
    third_tool.parent.mkdir(parents=True, exist_ok=True)
    third_tool.write_text("# mine - do not touch\n", encoding="utf-8")
    third_plugin = target / ".opencode" / "plugins" / "my-own-plugin.js"
    third_plugin.parent.mkdir(parents=True, exist_ok=True)
    third_plugin.write_text("// mine - do not touch\n", encoding="utf-8")

    assert agentic_sync.apply_plan(fw, target, manifest, force=False) == 0

    # Third-party files are untouched.
    assert third_tool.read_text(encoding="utf-8") == "# mine - do not touch\n"
    assert third_plugin.read_text(encoding="utf-8") == "// mine - do not touch\n"

    # They are not in the lockfile (not framework-managed).
    lock = json.loads((target / ".agentic.lock.json").read_text(encoding="utf-8"))
    assert ".agentic/tools/my-own-tool.py" not in lock["managed_files"]
    assert ".opencode/plugins/my-own-plugin.js" not in lock["managed_files"]

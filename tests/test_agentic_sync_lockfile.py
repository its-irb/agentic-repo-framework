"""Regression tests for ``bin/agentic-sync.py`` lockfile handling.

These tests verify that ``agentic-sync`` only manages the lockfile keys it owns
(``framework_version``, ``installed_at``, ``source``, ``managed_core_skills``,
``managed_files``, ``framework_remote_url``, ``framework_branch``,
``framework_commit``) and preserves any other top-level keys written by
external components such as ``docs-init`` / ``docs-update`` (e.g.
``documentation``).

They also verify that an existing lockfile that is not valid JSON (or whose
root is not a JSON object) is never overwritten and causes the sync to halt
with a clear error.
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


def _git_init(path: Path) -> None:
    """Initialize a minimal git repo so ``validate_basic_target`` accepts it."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


@pytest.fixture()
def agentic_sync():
    return _load_agentic_sync()


@pytest.fixture()
def target_repo(tmp_path):
    target = tmp_path / "consumer"
    target.mkdir()
    _git_init(target)
    return target


def test_apply_preserves_external_lockfile_keys(agentic_sync, target_repo, monkeypatch):
    """Regression: ``documentation`` and unknown keys must survive ``--apply``.

    Previously ``apply_plan`` rebuilt the lockfile from scratch and dropped
    every key not owned by agentic-sync, breaking ``docs-update`` which relies
    on the ``documentation`` baseline.
    """
    framework_root = agentic_sync.find_framework_root()
    manifest = agentic_sync.load_manifest(framework_root)

    # Stub the canonical GitHub resolver so the test is offline and
    # deterministic. apply_plan still exercises git introspection (branch,
    # commit, configured origin) and lockfile handling; only the network step
    # is replaced.
    canonical_url = "https://github.com/test/agentic-repo-framework.git"
    monkeypatch.setattr(
        agentic_sync,
        "_resolve_github_canonical",
        lambda owner, repo: canonical_url,
    )

    documentation = {
        "last_reviewed_commit": "abc123deadbeef0000000000000000000000000",
        "last_reviewed_at": "2026-07-17T10:38:11Z",
    }
    pre_existing = {
        "documentation": documentation,
        "custom_tool": {"nested": [1, 2, 3], "flag": True},
    }
    lockfile_path = target_repo / ".agentic.lock.json"
    lockfile_path.write_text(
        json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8"
    )

    exit_code = agentic_sync.apply_plan(framework_root, target_repo, manifest, force=False)
    assert exit_code == 0

    result = json.loads(lockfile_path.read_text(encoding="utf-8"))

    # Managed keys are present and updated.
    assert result["framework_version"] == manifest["framework_version"]
    assert result["source"] == str(framework_root)
    assert result["managed_core_skills"] == agentic_sync.discover_core_skills(framework_root)
    assert "installed_at" in result and result["installed_at"]
    assert isinstance(result["managed_files"], dict) and len(result["managed_files"]) > 0

    # External ``documentation`` key is preserved exactly.
    assert result["documentation"] == documentation

    # Unknown external keys are also preserved.
    assert result["custom_tool"] == pre_existing["custom_tool"]

    # Only the managed keys plus the external keys are present (no drops).
    expected_top_level = set(pre_existing.keys()) | {
        "framework_version",
        "installed_at",
        "source",
        "managed_core_skills",
        "managed_files",
        "framework_remote_url",
        "framework_branch",
        "framework_commit",
    }
    assert set(result.keys()) == expected_top_level

    # Traceability keys: URL comes from the (stubbed) canonical resolver;
    # branch and commit come from the framework git repo.
    assert result["framework_remote_url"] == canonical_url
    assert result["framework_branch"] == subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=framework_root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert result["framework_commit"] == subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=framework_root, capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.mark.parametrize(
    "invalid_content, kind",
    [
        ("{ this is not valid json", "invalid JSON"),
        ('["not", "an", "object"]', "not a JSON object"),
        ('"a plain string"', "not a JSON object"),
        ("42", "not a JSON object"),
    ],
)
def test_apply_halts_on_invalid_lockfile_without_overwriting(
    agentic_sync, target_repo, invalid_content, kind
):
    """An existing invalid lockfile must not be overwritten; sync must halt.

    Exercises both an unparseable file and valid JSON whose root is not an
    object. The file content must remain byte-for-byte identical afterwards.
    """
    framework_root = agentic_sync.find_framework_root()
    manifest = agentic_sync.load_manifest(framework_root)

    lockfile_path = target_repo / ".agentic.lock.json"
    lockfile_path.write_text(invalid_content, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        agentic_sync.apply_plan(framework_root, target_repo, manifest, force=False)

    message = str(exc_info.value)
    assert lockfile_path.name in message
    assert "will not overwrite" in message

    # The lockfile is untouched.
    assert lockfile_path.read_text(encoding="utf-8") == invalid_content
    # No temp file left behind.
    assert not (target_repo / ".agentic.lock.json.tmp").exists()


def test_apply_invalid_lockfile_halts_via_cli(target_repo):
    """End-to-end: the CLI exits non-zero and leaves the bad lockfile intact."""
    invalid_content = "{ broken json"

    lockfile_path = target_repo / ".agentic.lock.json"
    lockfile_path.write_text(invalid_content, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--apply", str(target_repo)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert ".agentic.lock.json" in result.stderr
    assert "will not overwrite" in result.stderr
    assert lockfile_path.read_text(encoding="utf-8") == invalid_content

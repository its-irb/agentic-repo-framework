# Operations

## Adding a new skill

1. Create the common implementation: `.agentic/skills/<name>/SKILL.md`
2. Create the wrapper for Claude Code: `.claude/skills/<name>/SKILL.md`
3. Create the wrapper for OpenCode: `.opencode/skills/<name>/SKILL.md`
4. Test `/<name>` in both harnesses.

## Syncing the framework to a consumer repository

```bash
python bin/agentic-sync.py --plan <target-path>
python bin/agentic-sync.py --apply <target-path>
python bin/agentic-sync.py --apply --force <target-path>
```

`--plan` shows what would be installed. `--apply` installs or updates files, leaving conflicts untouched. `--force` overwrites conflicting files with the framework versions. See [sync-model.md](sync-model.md) for details.

The canonical syntax is to place the action (`--plan` or `--apply`) before the target repository path.

## Updating documentation

When code changes affect architecture, APIs, or deployment, update the corresponding document in this directory in the same session. See [documentation-methodology.md](documentation-methodology.md) for principles.

## Adding a wrapper for a new harness

Create the directory structure `.harness-name/skills/<skill>/SKILL.md` with a file that points to the common implementation. No logic should be duplicated.

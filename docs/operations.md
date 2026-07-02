# Operations

## Adding a new skill

1. Create the common implementation: `.agentic/skills/<name>/SKILL.md`
2. Create the wrapper for Claude Code: `.claude/skills/<name>/SKILL.md`
3. Create the wrapper for OpenCode: `.opencode/skills/<name>/SKILL.md`
4. Test `/<name>` in both harnesses.

## Updating documentation

When code changes affect architecture, APIs, or deployment, update the corresponding document in this directory in the same session. See [documentation-methodology.md](documentation-methodology.md) for principles.

## Adding a wrapper for a new harness

Create the directory structure `.harness-name/skills/<skill>/SKILL.md` with a file that points to the common implementation. No logic should be duplicated.

# API

This framework does not expose a programmatic API. Its "interface" is the file convention that both harnesses follow.

## Skill invocation convention

When a harness encounters `/<skill-name>`:

1. It resolves the wrapper at `.claude/skills/<skill-name>/SKILL.md` (Claude Code) or `.opencode/skills/<skill-name>/SKILL.md` (OpenCode).
2. The wrapper points to the common implementation at `.agentic/skills/<skill-name>/SKILL.md`.

## Available skills

| Skill | Description |
|-------|-------------|
| `docs-init` | Generate minimal initial documentation |
| `docs-update` | Update documentation alongside code changes |
| `count-files` | Count files in a scope |
| `read-test-docs` | Read test documentation |
| `read-test-index` | Read the test index |

Additional skills can be added by following the structure in [architecture.md](architecture.md).

# Architecture

## Overview

The Agentic Repo Framework is a minimal framework for modular documentation oriented to coding agents. It defines two concepts:

1. **Skills** — reusable, harness-agnostic instructions stored in a single location.
2. **Wrappers** — harness-specific entry points that delegate to the common skill implementation.

## Directory structure

```
.agentic/skills/<skill>/SKILL.md    ← common implementation
.claude/skills/<skill>/SKILL.md    ← Claude Code wrapper
.opencode/skills/<skill>/SKILL.md  ← OpenCode wrapper
```

## Flow

1. The user invokes `/<skill>` in a harness.
2. The harness loads the wrapper for its platform.
3. The wrapper delegates to the common implementation at `.agentic/skills/<skill>/SKILL.md`.

## Framework sync

The framework can be installed and updated in consumer repositories using `bin/agentic-sync.py`. It manages:

- Core skills (`.agentic/skills/`)
- Wrapper skills (`.claude/skills/`, `.opencode/skills/`)
- Common documentation (`docs/documentation-methodology.md`)

A manifest file (`.agentic-framework.json`) declares the framework version, managed files and managed skill roots. Each consumer repository receives a lockfile (`.agentic.lock.json`) tracking what was installed.

See [sync-model.md](sync-model.md) for the full sync model.

## Key design decision

Skills are written once and shared across all harnesses. Wrappers contain no business logic — they only define how a harness discovers and invokes the common skill.

# Agentic Repo Framework

Framework mínimo para orquestar skills y documentación orientada a agentes de coding.

## Qué es

Un conjunto de convenciones y ficheros que permiten añadir skills reutilizables a un repositorio y que distintos arneses (Claude, OpenCode, etc.) las ejecuten de forma uniforme.

## Funcionalidades

- Skills centralizadas en `.agentic/skills/<skill>/SKILL.md`
- Wrappers específicos por arnés en `.claude/skills/` y `.opencode/skills/`
- Lockfile de seguimiento (`agentic.lock.json`) para documentación y cambios
- Metodología de documentación mínima para mantener agentes ligeros

## Estructura

```text
.agentic/skills/       # lógica de cada skill
.claude/skills/        # wrapper para Claude
.opencode/skills/      # wrapper para OpenCode
docs/                  # documentación del proyecto
```

## Cómo usar

1. Añade una skill en `.agentic/skills/<nombre>/SKILL.md`
2. Crea los wrappers necesarios para tus arneses
3. Consulta la metodología de documentación en `docs/documentation-methodology.md`

## Documentación

- [Metodología de documentación](docs/documentation-methodology.md)

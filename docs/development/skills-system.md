# Sistema de skills

## Objetivo

El framework mantiene una única implementación de cada skill, independientemente
del arnés utilizado (Claude Code u OpenCode). La lógica común nunca se duplica.

> El índice operativo canónico del sistema de skills es `.agentic/SKILLS.md`,
> conservado en la raíz del framework. Este documento lo desarrolla para
> desarrolladores y mantenedores.

## Estructura

```text
.agentic/
└── skills/
    └── <skill>/
        └── SKILL.md      # implementación común

.claude/
└── skills/
    └── <skill>/
        └── SKILL.md      # wrapper Claude Code

.opencode/
└── skills/
    └── <skill>/
        └── SKILL.md      # wrapper OpenCode
```

## Funcionamiento

Cuando el usuario ejecuta `/<skill>`, el arnés carga el wrapper correspondiente.
El wrapper únicamente redirige a la implementación común situada en
`.agentic/skills/<skill>/SKILL.md`. Toda la lógica de la skill reside
exclusivamente en ese documento.

## Contenido de un wrapper

Un wrapper contiene:

- Frontmatter con `name` y `description`.
- Opcionalmente, restricciones de herramientas (p. ej. `allowed-tools` en el
  wrapper de Claude Code).
- Una indicación de seguir las instrucciones comunes en
  `.agentic/skills/<skill>/SKILL.md`.

No contiene lógica de negocio. Ejemplo esquemático:

```markdown
---
name: mi-skill
description: Descripción breve.
---

Sigue las instrucciones comunes en:

.agentic/skills/mi-skill/SKILL.md
```

## Skills core disponibles

| Skill | Descripción |
|-------|-------------|
| `commit-work` | Revisa cambios, actualiza/valida las capas documentales y prepara un commit descriptivo. |
| `docs-init` | Inicializa, adapta o completa la documentación integral del repositorio (capas para agentes, desarrolladores y usuarios) y valida el README. |
| `docs-update` | Revisa los cambios desde el último commit documentado, actualiza las capas y verifica su coherencia con el README. |

## Principios

- Una única implementación por skill.
- Un wrapper por arnés soportado.
- Los wrappers no contienen lógica de negocio.
- La implementación común debe ser independiente del arnés siempre que sea
  posible.

## Añadir una nueva skill core

1. Crear `.agentic/skills/<nombre>/SKILL.md` con la implementación común.
2. Crear el wrapper para Claude Code: `.claude/skills/<nombre>/SKILL.md`.
3. Crear el wrapper para OpenCode: `.opencode/skills/<nombre>/SKILL.md`.
4. Verificar que `/<nombre>` funciona en ambos arneses.

Al ser una Core Skill, se distribuye a los repos consumidores mediante
`agentic-sync` (ver [sync-model.md](sync-model.md)). El descubrimiento de skills
en `agentic-sync` escanea `.agentic/skills/*/SKILL.md`, por lo que crear el
directorio con su `SKILL.md` basta para que quede gestionada.

## Añadir un wrapper para un arnés nuevo

Crear la estructura `<harness>/skills/<skill>/SKILL.md` con un fichero que
redirija a la implementación común. No duplicar lógica. Para que `agentic-sync`
lo gestione, añade la raíz del arnés a `managed_skill_roots` en
`.agentic-framework.json`.

## Cuándo modificar cada archivo

**Implementación común** (`.agentic/skills/<skill>/SKILL.md`): modificar cuando
cambia el comportamiento de la skill.

**Wrapper**: modificar únicamente cuando cambie la forma en que un arnés invoca
las skills (p. ej. nuevos campos de frontmatter, nuevas restricciones de
herramientas). No modificar el wrapper para cambiar el comportamiento de la
skill; para eso, modifica la implementación común.

## Skills en repos consumidores

En un repositorio consumidor coexisten tres tipos de skills:

- **Core Skills**: instaladas y actualizadas por `agentic-sync`. Se sobrescriben
  con la versión del framework.
- **Repo Skills**: creadas por el equipo del repositorio, versionadas con él.
  `agentic-sync` nunca las modifica.
- **Personal Skills**: creadas por un usuario para sí mismo, no compartidas.
  `agentic-sync` nunca las modifica.

La distinción entre Core y Repo/Personal se basa en la ubicación y en el
manifest: `agentic-sync` solo gestiona las skills descubiertas bajo las raíces
declaradas y las lista como `managed_core_skills`. Ver [sync-model.md](sync-model.md).

# Skills (agentes)

## Convención de invocación

Al ejecutar `/<skill-name>` en un arnés:

1. El arnés resuelve el wrapper:
   - Claude Code → `.claude/skills/<skill-name>/SKILL.md`
   - OpenCode → `.opencode/skills/<skill-name>/SKILL.md`
2. El wrapper redirige a la implementación común:
   `.agentic/skills/<skill-name>/SKILL.md`
3. Toda la lógica reside en esa implementación común.

## Skills core disponibles

| Skill | Descripción |
|-------|-------------|
| `commit-work` | Revisa cambios, actualiza/valida las capas documentales y prepara un commit descriptivo. |
| `docs-init` | Inicializa, adapta o completa la documentación integral del repositorio (capas para agentes, desarrolladores y usuarios) y valida el README. |
| `docs-update` | Revisa los cambios desde el último commit documentado, propone las actualizaciones en las capas, las aplica tras confirmación humana explícita y verifica su coherencia con el README. |

Estas tres skills son **Core Skills**: las mantiene el framework y se
instalan/actualizan con `agentic-sync`.

## Estructura de una skill

```text
.agentic/skills/<skill>/SKILL.md      # implementación común (lógica)
.claude/skills/<skill>/SKILL.md       # wrapper Claude Code
.opencode/skills/<skill>/SKILL.md     # wrapper OpenCode
```

Un wrapper típico contiene frontmatter (`name`, `description`) y una línea que
indica "Sigue las instrucciones comunes en `.agentic/skills/<skill>/SKILL.md`".
El wrapper de Claude Code puede añadir `allowed-tools` en el frontmatter.

## Añadir una nueva skill core

1. Crea `.agentic/skills/<nombre>/SKILL.md` con la lógica.
2. Crea los wrappers en `.claude/skills/<nombre>/SKILL.md` y
   `.opencode/skills/<nombre>/SKILL.md` (sin lógica de negocio).
3. Verifica que `/<nombre>` funciona en ambos arneses.

Si la skill debe distribuirse a consumidores, se gestiona como Core Skill vía
`agentic-sync`. Para skills de un repositorio consumidor (Repo Skills o
Personales) no uses sync; ver `docs/user/skills.md`.

## Cuándo modificar cada fichero

- **Implementación común** (` .agentic/skills/<skill>/SKILL.md`): cuando cambia
  el comportamiento de la skill.
- **Wrapper**: solo cuando cambia la forma en que un arnés invoca skills.

## Referencia operativa

`.agentic/SKILLS.md` es el índice operativo del sistema de skills (se conserva
en el repo; no se mueve).

# Arquitectura (agentes)

## Propósito

Agentic Repo Framework es un conjunto mínimo de convenciones y ficheros que
permite añadir **skills reutilizables** a un repositorio y que distintos arneses
(Claude Code, OpenCode) las ejecuten de forma uniforme, **sin duplicar la
lógica** en cada arnés.

## Conceptos

1. **Skill** — instrucciones reutilizables, independientes del arnés. Existe una
   única implementación por skill.
2. **Wrapper** — punto de entrada específico de un arnés. Solo redirige a la
   implementación común. No contiene lógica de negocio.

## Rutas relevantes

```text
.agentic/skills/<skill>/SKILL.md      # implementación común (única fuente de lógica)
.claude/skills/<skill>/SKILL.md       # wrapper Claude Code
.opencode/skills/<skill>/SKILL.md     # wrapper OpenCode
bin/agentic-sync.py                   # instala/actualiza el framework en repos consumidores
.agentic-framework.json               # manifest: versión, archivos gestionados, raíces de skills
.agentic.lock.json                    # baseline documental (en este repo) / estado instalado (en consumidores)
docs/documentation-methodology.md     # metodología documental (archivo GESTIONADO por sync)
```

`docs/documentation-methodology.md` está declarado en `managed_files` del
manifest. No lo muevas ni lo trates como documentación libre.

## Interfaz de invocación

El usuario ejecuta `/<skill-name>` en un arnés. El arnés carga su wrapper, que
redirige a `.agentic/skills/<skill-name>/SKILL.md`. Toda la lógica reside en ese
fichero común.

## Invariantes

- Una única implementación por skill, en `.agentic/skills/`.
- Un wrapper por arnés soportado; los wrappers no contienen lógica de negocio.
- La implementación común es independiente del arnés siempre que sea posible.
- `.agentic-framework.json` es el manifest canónico del framework.
- `bin/agentic-sync.py` solo gestiona **Core Skills**, wrappers de Core Skills,
  `docs/documentation-methodology.md`, la herramienta
  `.agentic/tools/check-framework-updates.py` y el plugin de OpenCode
  `.opencode/plugins/agentic-update-check.js`. Nunca toca Repo Skills ni
  Personal Skills.

## Convenciones

- Las skills comunes viven una única vez en `.agentic/skills/`.
- Los wrappers solo cambian cuando cambia la forma en que un arnés invoca skills.
- La documentación se organiza en tres capas: `docs/agent/`, `docs/development/`,
  `docs/user/`. Ver `docs/documentation-methodology.md` para los principios.
- Las referencias a documentación usan rutas normales del repositorio
  (p. ej. `docs/agent/architecture.md`), no sintaxis de arnés tipo `@docs/...`.

## Componentes operativos (no tocar como documentación)

Estos ficheros cumplen una función operativa y no deben moverse ni eliminarse
aunque su contenido también se explique en la documentación:

- `.agentic-framework.json` — manifest.
- `.agentic.lock.json` — lockfile / baseline documental.
- `.agentic/SKILLS.md` — índice operativo del sistema de skills.
- `.agentic|claude|opencode/skills/*/SKILL.md` — skills y wrappers.
- `.agentic/test-skills/`, `.agentic/test-docs/` y sus espejos en
  `.claude/test-skills/`, `.opencode/test-skills/` — fixtures de test.

## Sincronización

El framework se instala/actualiza en repos consumidores mediante
`bin/agentic-sync.py`. El detalle está en [sync.md](sync.md).

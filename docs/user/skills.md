# Skills

## Cómo se invocan

En tu arnés, ejecuta `/<skill-name>`. El arnés carga su wrapper y este redirige
a la implementación común. Toda la lógica vive una sola vez en el framework.

- Claude Code usa `.claude/skills/<skill>/SKILL.md`.
- OpenCode usa `.opencode/skills/<skill>/SKILL.md`.
- Ambos delegan en `.agentic/skills/<skill>/SKILL.md`.

## Skills core disponibles

Estas skills vienen con el framework y se instalan mediante `agentic-sync`:

| Skill | Descripción |
|-------|-------------|
| `commit-work` | Revisa cambios, actualiza/valida la documentación y prepara un commit descriptivo. |
| `docs-init` | Genera, adapta o completa la documentación integral del repositorio (agentes, desarrolladores, usuarios) y valida el README. |
| `docs-update` | Revisa los cambios desde el último commit documentado, propone las actualizaciones necesarias y las aplica tras confirmación humana explícita. |

### Uso típico

- `/docs-init` — la primera vez, para crear la documentación del repo consumidor
  siguiendo la metodología de tres capas.
- `/docs-update` — tras cambios de código, para revisar y actualizar la
  documentación afectada.
- `/commit-work` — para preparar un commit revisando también el estado
  documental.

## Tipos de skills

En un repositorio consumidor coexisten tres tipos:

1. **Core Skills**: las mantiene el framework y se instalan/actualizan con
   `agentic-sync`. Las de la tabla anterior.
2. **Repo Skills**: las crea el equipo del repositorio, se versionan con él y
   están disponibles para todo el equipo. `agentic-sync` no las modifica.
3. **Personal Skills**: las crea un usuario para sí mismo, no se comparten.
   `agentic-sync` no las modifica.

> La versión actual (**v0**) solo gestiona Core Skills con `agentic-sync`. Las
> Repo y Personales se definen por convención y se mantienen a mano.

## Añadir una skill propia (Repo o Personal)

Sigue la misma estructura que las Core Skills:

1. Crea `.agentic/skills/<nombre>/SKILL.md` con la implementación común.
2. Crea los wrappers que necesites en `.claude/skills/<nombre>/SKILL.md` y/o
   `.opencode/skills/<nombre>/SKILL.md` (sin lógica de negocio, solo
   redirigiendo a la implementación común).
3. Verifica que `/<nombre>` funciona en tu arnés.

Si es una **Repo Skill**, commit al repositorio para compartirla con el equipo.
Si es **Personal**, mantenla fuera del control de versiones o en un espacio
personal.

Importante: `agentic-sync` podría sobrescribir `.agentic/skills/` si tus skills
propias colisionan con nombres de Core Skills. Usa nombres distintos a los de
las Core Skills (`commit-work`, `docs-init`, `docs-update`).

## Mantener las skills actualizadas

Las Core Skills se actualizan volviendo a sincronizar el framework:

```bash
python bin/agentic-sync.py --plan <target>
python bin/agentic-sync.py --apply <target>
```

Si modificaste una Core Skill localmente, aparecerá como `CONFLICT` y no se
sobrescribirá salvo que uses `--force`. Ver [sync-guide.md](sync-guide.md).

## Limitaciones

- No hay API programática; las skills son documentos de instrucciones.
- Los wrappers deben redirigir a la implementación común; no deben contener
  lógica de negocio.

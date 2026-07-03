# Agentic Repo Framework

Framework mínimo para orquestar skills y documentación orientada a agentes de coding.

## Qué es

Un conjunto de convenciones y ficheros que permiten añadir skills reutilizables a un repositorio y que distintos arneses (Claude, OpenCode, etc.) las ejecuten de forma uniforme. Resuelve el problema de mantener instrucciones reutilizables para agentes sin duplicarlas en cada arnés.

## Funcionalidades

- Skills centralizadas en `.agentic/skills/<skill>/SKILL.md`
- Wrappers específicos por arnés en `.claude/skills/` y `.opencode/skills/`
- Lockfile de seguimiento (`.agentic.lock.json`) para documentación y cambios
- Metodología de documentación mínima para mantener agentes ligeros
- Sincronización del framework en repos consumidores (`bin/agentic-sync.py`)
- Manifest de configuración (`.agentic-framework.json`)

## Estructura

```text
.agentic/skills/       # lógica de cada skill
.claude/skills/        # wrapper para Claude
.opencode/skills/      # wrapper para OpenCode
bin/                   # scripts del framework
docs/                  # documentación del proyecto
.agentic-framework.json  # manifest del framework
```

## Instalación en un repositorio consumidor

```bash
python bin/agentic-sync.py --plan <target-path>
python bin/agentic-sync.py --apply <target-path>
```

`--plan` muestra qué se instalaría. `--apply` instala o actualiza los archivos gestionados.

## Cómo usar

1. Añade una skill en `.agentic/skills/<nombre>/SKILL.md`
2. Crea los wrappers necesarios para tus arneses
3. Instala el framework en un repositorio consumidor con `bin/agentic-sync.py`
4. Consulta la metodología de documentación en `docs/documentation-methodology.md`

## Documentación

- [Metodología de documentación](docs/documentation-methodology.md)
- [Arquitectura](docs/architecture.md)
- [API (convenciones)](docs/api.md)
- [Operaciones](docs/operations.md)
- [Modelo de sincronización](docs/sync-model.md)
- [Documentación completa](docs/README.md)

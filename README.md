# Agentic Repo Framework

Framework mínimo para orquestar skills y documentación orientada a agentes de
coding, de forma independiente del arnés (Claude Code, OpenCode, etc.).

## Qué es

Un conjunto de convenciones y ficheros que permite añadir skills reutilizables a
un repositorio y que distintos arneses las ejecuten de forma uniforme. Resuelve
el problema de mantener instrucciones reutilizables para agentes **sin
duplicarlas** en cada arnés.

La lógica de cada skill vive una única vez en `.agentic/skills/`; cada arnés la
descubre mediante un wrapper mínimo que redirige a ella.

## Funcionalidades

- Skills centralizadas en `.agentic/skills/<skill>/SKILL.md` (implementación
  común única).
- Wrappers específicos por arnés en `.claude/skills/` y `.opencode/skills/` (sin
  lógica de negocio).
- Sincronización del framework en repos consumidores con `bin/agentic-sync.py`.
- Manifest de configuración (`.agentic-framework.json`).
- Lockfile (`.agentic.lock.json`) con propósito dual: baseline documental en el
  framework y estado instalado en consumidores.
- Metodología de documentación en tres capas (agentes, desarrollo, usuarios).

## Requisitos

- Git (el framework y los targets deben ser repositorios git).
- Python 3 (para `bin/agentic-sync.py`; solo biblioteca estándar, sin
  dependencias).
- Un arnés soportado (Claude Code u OpenCode) para invocar skills.

## Estructura

```text
.agentic/skills/           # implementación común de cada skill
.claude/skills/            # wrappers para Claude Code
.opencode/skills/          # wrappers para OpenCode
bin/agentic-sync.py        # sincroniza el framework en repos consumidores
docs/                      # documentación en tres capas
├── agent/                 # capa compacta para agentes
├── development/           # capa técnica para desarrollo
├── user/                  # capa de uso
└── documentation-methodology.md  # metodología (gestionada por sync)
.agentic-framework.json    # manifest del framework (versión, archivos gestionados)
.agentic.lock.json         # baseline documental / estado instalado
```

## Instalación en un repositorio consumidor

```bash
python bin/agentic-sync.py --plan <target>
python bin/agentic-sync.py --apply <target>
```

- `--plan` muestra qué se instalaría sin modificar el target.
- `--apply` instala o actualiza los archivos gestionados (deja los conflictos
  intactos).
- `--apply --force` sobrescribe los conflictos con la versión del framework.

La sintaxis canónica coloca la acción antes de la ruta del target. Ver
[docs/user/sync-guide.md](docs/user/sync-guide.md) para el detalle.

## Uso

1. Sincroniza el framework en tu repositorio con `bin/agentic-sync.py`.
2. Invoca las skills core en tu arnés (p. ej. `/docs-init` para generar la
   documentación inicial).
3. Añade tus propias skills en `.agentic/skills/<nombre>/SKILL.md` con sus
   wrappers.

### Skills core

| Skill | Descripción |
|-------|-------------|
| `commit-work` | Revisa cambios, actualiza/valida documentación y prepara un commit descriptivo. |
| `docs-init` | Genera, adapta o completa la documentación integral (agentes, desarrollo, usuarios) y valida el README. |
| `docs-update` | Revisa los cambios desde el último commit documentado, propone las actualizaciones necesarias y las aplica tras confirmación humana explícita. |

## Documentación

- [Documentación para usuarios](docs/user/README.md) — instalación, sincronización y skills.
- [Documentación para desarrollo](docs/development/README.md) — arquitectura, sistema de skills, modelo de sincronización y operaciones.
- [Documentación para agentes](docs/agent/README.md) — capa compacta y modular.
- [Metodología de documentación](docs/documentation-methodology.md) — principios de mantenimiento documental.

## Estado

Versión `0.1.0` (modelo v0: solo soporte para Core Skills gestionadas por sync).

## Licencia

[MIT](LICENSE).

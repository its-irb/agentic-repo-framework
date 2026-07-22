# Arquitectura

## Intención

Agentic Repo Framework resuelve un problema concreto: mantener instrucciones
reutilizables para agentes de coding (skills) **sin duplicarlas** en cada arnés.

Antes de este framework, añadir una skill a un repositorio que usa varios arneses
(Claude Code, OpenCode, etc.) obligaba a mantener copias independientes de la
misma lógica en cada convención de arnés. Cualquier cambio había que replicarlo a
mano en cada sitio.

El framework propone una única implementación por skill y wrappers mínimos que
únicamente redirigen a ella.

## Conceptos

1. **Skill** — instrucciones reutilizables, independientes del arnés. Una única
   implementación por skill.
2. **Wrapper** — punto de entrada específico de un arnés. Delega en la
   implementación común. No contiene lógica de negocio.

La separación permite que la lógica viva una sola vez y que cada arnés la
descubra con su propia convención de directorios.

## Estructura del repositorio

```text
.agentic/skills/<skill>/SKILL.md     # implementación común (única fuente de lógica)
.claude/skills/<skill>/SKILL.md      # wrapper Claude Code
.opencode/skills/<skill>/SKILL.md    # wrapper OpenCode
.agentic/SKILLS.md                    # índice operativo del sistema de skills
bin/agentic-sync.py                   # instala/actualiza el framework en consumidores
.agentic-framework.json               # manifest del framework
.agentic.lock.json                    # baseline documental (framework) / estado instalado (consumidores)
docs/                                 # documentación en tres capas
├── agent/                            # capa compacta para agentes
├── development/                      # capa técnica (este directorio)
├── user/                             # capa de uso
└── documentation-methodology.md      # metodología (GESTIONADA por sync)
```

Los fixtures de test (`test-skills/`, `test-docs/`) existen en `.agentic/` y se
espejan en `.claude/` y `.opencode/` para verificar la resolución de wrappers en
ambos arneses.

## Flujo de invocación

1. El usuario ejecuta `/<skill>` en un arnés.
2. El arnés carga el wrapper correspondiente a su plataforma.
3. El wrapper delega en la implementación común situada en
   `.agentic/skills/<skill>/SKILL.md`.

Toda la lógica de la skill reside exclusivamente en ese documento común. Los
wrappers no implementan comportamiento.

## Framework sync

El framework se instala y actualiza en repos consumidores mediante
`bin/agentic-sync.py`, que gestiona:

- Core Skills (`.agentic/skills/`).
- Wrappers de Core Skills (`.claude/skills/`, `.opencode/skills/`).
- `docs/documentation-methodology.md`.
- La herramienta de comprobación `.agentic/tools/check-framework-updates.py`.
- El plugin de OpenCode `.opencode/plugins/agentic-update-check.js`.

Un manifest (`.agentic-framework.json`) declara la versión del framework, los
archivos gestionados explícitamente y las raíces de skills a escanear. Cada
repositorio consumidor recibe un lockfile (`.agentic.lock.json`) que registra lo
instalado.

El detalle del modelo de sincronización está en [sync-model.md](sync-model.md).

## Decisiones de diseño

### Skills escritas una vez, compartidas por todos los arneses

La lógica común nunca se duplica. Los wrappers contienen exclusivamente la
forma en que un arnés descubre e invoca la skill común. Esto reduce el
mantenimiento y evita divergencias entre arneses.

### Separación de tipos de skills

Existen tres niveles de evolución (ver [sync-model.md](sync-model.md)):

- **Core**: mantenidas por el framework, instaladas vía `agentic-sync`.
- **Repo**: creadas por el equipo del repositorio consumidor, versionadas con él,
  no gestionadas por sync.
- **Personal**: creadas por un usuario para sí mismo, no compartidas, no
  gestionadas por sync.

La versión inicial (**v0**) implementa únicamente soporte para Core Skills.

### Lockfile con propósito dual

El mismo fichero `.agentic.lock.json` cumple funciones distintas según el
repositorio:

- En el **framework**: rastrea el baseline de revisión documental (usado por
  `docs-update`).
- En **consumidores**: registra el estado instalado del framework (versión,
  archivos gestionados, hashes SHA-256 y trazabilidad del origen: URL del
  remoto, rama y commit aplicados) además de la revisión documental.

### Metodología documental como archivo gestionado

`docs/documentation-methodology.md` es un archivo gestionado por sync porque es
parte del contrato común del framework, no documentación específica de un
repositorio. Por eso vive en `managed_files` del manifest y se distribuye a los
consumidores.

### Tres capas documentales independientes

La documentación se organiza en tres capas (`docs/agent/`, `docs/development/`,
`docs/user/`) que derivan del conocimiento verificado del repositorio, no unas de
otras. Cada capa es autosuficiente para su audiencia; la redundancia entre capas
es aceptable cuando preserva esa autosuficiencia. Ver
`docs/documentation-methodology.md`.

## Superficie pública

El framework no expone una API programática. Su "interfaz" es la convención de
ficheros que siguen los arneses, más el CLI `bin/agentic-sync.py` para
instalarlo en consumidores.

## Estado y madurez

Versión del framework: `0.1.0` (declarada en `.agentic-framework.json`).
Modelo v0: solo soporte para Core Skills.

# Primeros pasos

## Qué es Agentic Repo Framework

Un conjunto mínimo de convenciones y ficheros que permite añadir **skills
reutilizables** a un repositorio y que distintos arneses de coding (Claude Code,
OpenCode) las ejecuten de forma uniforme.

Una *skill* es un conjunto de instrucciones reutilizables para agentes de
coding. El framework evita duplicar la misma lógica en cada arnés: la
implementación vive una sola vez y cada arnés la descubre mediante un *wrapper*
mínimo que redirige a ella.

## Qué problema resuelve

Mantener instrucciones reutilizables para agentes sin copiarlas en cada arnés.
Antes, añadir una skill a un repo con varios arneses obligaba a mantener copias
independientes de la misma lógica; cualquier cambio había que replicarlo a mano
en cada sitio.

## Para quién está pensado

- Equipos que usan uno o varios arneses de coding (Claude Code, OpenCode) y
  quieren mantener skills compartidas y versionadas.
- Repositorios que quieren una metodología documental ligera orientada a agentes.

No requiere conocimientos avanzados más allá de Git y la línea de comandos.

## Requisitos

- **Git**: el framework y los repositorios donde se instale deben ser
  repositorios git.
- **Python 3**: para ejecutar el script de sincronización
  `bin/agentic-sync.py`. No necesita dependencias externas; usa solo la
  biblioteca estándar.
- **Un arnés soportado** (Claude Code o OpenCode) si quieres invocar skills.

## Instalación en un repositorio consumidor

El framework se instala **sincronizándolo** desde este repositorio hacia el
repositorio consumidor con `bin/agentic-sync.py`.

1. Previsualiza lo que se instalaría:

   ```bash
   python bin/agentic-sync.py --plan <ruta-del-repo-consumidor>
   ```

2. Instala o actualiza los archivos gestionados:

   ```bash
   python bin/agentic-sync.py --apply <ruta-del-repo-consumidor>
   ```

`--apply` copia los archivos del framework al repo consumidor y genera allí un
lockfile `.agentic.lock.json` con el estado instalado. No sobrescribe cambios
locales conflictivos (usa `--force` solo si lo necesitas; ver
[sync-guide.md](sync-guide.md)).

La sintaxis canónica coloca la acción (`--plan` o `--apply`) **antes** de la ruta
del repositorio target.

## Qué se instala

En el repositorio consumidor se instalan:

- Las **Core Skills** en `.agentic/skills/`.
- Los **wrappers** en `.claude/skills/` y `.opencode/skills/`.
- La **metodología documental** en `docs/documentation-methodology.md`.

No se instala nada más. La documentación específica del repo consumidor y sus
skills propias no se tocan.

## Primeros pasos tras instalar

1. Invoca una skill core en tu arnés, por ejemplo `/docs-init` para generar la
   documentación inicial del repo consumidor siguiendo la metodología.
2. Consulta [skills.md](skills.md) para ver las skills core disponibles.
3. Consulta [sync-guide.md](sync-guide.md) para mantener el framework actualizado
   en el repo consumidor.

## Limitaciones

- La versión actual (**v0**) solo soporta **Core Skills**: las Repo Skills y
  Personales están definidas conceptualmente pero no gestionadas por sync.
- No hay API programática; la integración es por convención de ficheros y por el
  CLI de sincronización.
- El formato del lockfile de consumidor puede evolucionar en futuras versiones.

## Soporte y licencia

- Licencia: MIT (ver `LICENSE`).
- Para detalles técnicos y de mantenimiento, consulta `docs/development/`.

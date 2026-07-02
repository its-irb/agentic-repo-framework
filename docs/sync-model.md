# Modelo de sincronización

## Objetivo

Instalar y actualizar herramientas agentic comunes en repos consumidores.

## Archivos gestionados

- .agentic/skills/
- .claude/skills/
- .opencode/skills/
- docs/documentation-methodology.md

## Lockfile

Cada repo consumidor tendrá:

.agentic.lock.json

Campos mínimos:

- framework_version
- installed_at
- source
- managed_files

## Reglas

- No sobrescribir cambios locales sin mostrar diff.
- El framework no toca documentación específica del repo consumidor.
- El framework solo gestiona metodología, skills comunes y wrappers por arnés.
# Modelo de sincronización

## Objetivo

Instalar y actualizar las funcionalidades comunes del Agentic Repo Framework en repos consumidores, manteniendo separadas las funcionalidades propias de cada repositorio y las personalizaciones de cada usuario.

## Tipos de skills

Existen tres niveles de evolución para una skill:

1. **Core**
   - Forma parte del Agentic Repo Framework.
   - Es mantenida por el framework.
   - Se instala y actualiza mediante `agentic-sync`.

2. **Repo**
   - Ha sido creada por un usuario del repositorio.
   - Está disponible para todo el equipo.
   - Se versiona junto con el repositorio.
   - No es gestionada por `agentic-sync`.

3. **Personal**
   - Ha sido creada por un usuario para su propio uso.
   - No se comparte con el equipo.
   - No es gestionada por `agentic-sync`.

La versión inicial del framework (**v0**) implementa únicamente el soporte para **Core Skills**.

## Archivos gestionados

En la versión inicial, `agentic-sync` solo gestiona:

- `.agentic/skills/` (únicamente las Core Skills)
- `.claude/skills/` (wrappers de Core Skills)
- `.opencode/skills/` (wrappers de Core Skills)
- `docs/documentation-methodology.md`

No gestiona ningún otro archivo del repositorio.

## Lockfile

Cada repositorio consumidor contiene un fichero:

```text
.agentic.lock.json
```

Campos mínimos:

- `framework_version`
- `installed_at`
- `source`
- `managed_core_skills`

En futuras versiones podrá ampliarse con información sobre Repo Skills y otros componentes del framework.

## Reglas

- `agentic-sync` solo instala y actualiza Core Skills.
- Nunca modifica Repo Skills.
- Nunca modifica Personal Skills.
- Nunca sobrescribe cambios locales sin mostrar previamente un diff.
- El framework no modifica la documentación específica del repositorio consumidor.
- El framework solo gestiona la metodología común, las Core Skills y los wrappers específicos de cada arnés.
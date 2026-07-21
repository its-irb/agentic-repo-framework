# Modelo de sincronización

## Objetivo

Instalar y actualizar las funcionalidades comunes del Agentic Repo Framework en
repos consumidores, manteniendo separadas las funcionalidades propias de cada
repositorio y las personalizaciones de cada usuario.

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

La versión inicial del framework (**v0**) implementa únicamente el soporte para
**Core Skills**.

## Archivos gestionados

En la versión inicial, `agentic-sync` solo gestiona:

- `.agentic/skills/` (únicamente las Core Skills)
- `.claude/skills/` (wrappers de Core Skills)
- `.opencode/skills/` (wrappers de Core Skills)
- `docs/documentation-methodology.md`

No gestiona ningún otro archivo del repositorio.

## Reglas

- `agentic-sync` solo instala y actualiza Core Skills.
- Nunca modifica Repo Skills.
- Nunca modifica Personal Skills.
- Nunca sobrescribe cambios locales sin mostrar previamente el estado (usa
  `--plan` para inspeccionar; `--apply` deja los conflictos intactos).
- El framework no modifica la documentación específica del repositorio
  consumidor.
- El framework solo gestiona la metodología común, las Core Skills y los
  wrappers específicos de cada arnés.

## CLI: `bin/agentic-sync.py`

### Sintaxis

```bash
python bin/agentic-sync.py --plan <target>
python bin/agentic-sync.py --apply <target>
python bin/agentic-sync.py --apply --force <target>
```

- La sintaxis canónica coloca la acción (`--plan` o `--apply`) **antes** de la
  ruta del repositorio target.
- `<target>` por defecto es `.` (directorio actual).
- El framework root se resuelve como el directorio abuelo del script
  (`bin/` → raíz del framework).

### Argumentos

| Argumento | Descripción |
|-----------|-------------|
| `--plan` | Previsualiza lo que se instalaría sin modificar el target. |
| `--apply` | Instala/actualiza archivos seguros en el target. |
| `--force` | Sobrescribe los ficheros en conflicto con la versión del framework (se usa con `--apply`). |
| `target` | Ruta del repositorio target. Por defecto `.`. |

### Validación previa

`validate_basic_target()` comprueba que:

- El framework root es un repositorio git.
- El target es un repositorio git.
- El target no es el propio repositorio framework.

Si alguna comprobación falla, se imprime el error a `stderr` y se devuelve
código de salida 1.

### Estados de un fichero gestionado

`file_status()` clasifica cada fichero comparando la fuente (framework), el
destino (target) y el hash guardado en el lockfile del target:

| Estado | Condición | Acción en `--apply` |
|--------|-----------|---------------------|
| `MISSING` | La fuente no existe en el framework. | Se omite. |
| `INSTALL` | Fuente existe, destino no. | Se copia. |
| `SKIP` | Hashes idénticos (fuente ≡ destino). | Nada. |
| `UPDATE` | Destino ≠ fuente, pero destino ≡ hash del lockfile. | Se sobrescribe (cambio seguro). |
| `CONFLICT` | Destino ≠ fuente y destino ≠ hash del lockfile. | Se deja intacto, salvo `--force`. |

El hash es SHA-256, calculado por bloques de 1 MB (`sha256_file()`).

### Salida

Tanto `--plan` como `--apply` imprimen:

- Cabecera con versión, framework root y target.
- Lista de Core Skills detectadas (`discover_core_skills`).
- Lista de archivos con su estado.
- Resumen con contadores de `install`, `update`, `skip`, `conflict` y
  `missing`.

`--apply` además imprime, por archivo, la acción realizada (`INSTALL`, `UPDATE`,
`SKIP`, `FORCE`, `CONFLICT`, `MISSING`) y escribe el lockfile del target.

## Manifest (`.agentic-framework.json`)

Declara:

- `framework_version`: versión del framework (actualmente `0.1.0`).
- `managed_files`: archivos gestionados explícitos (actualmente
  `docs/documentation-methodology.md`).
- `managed_skill_roots`: raíces a escanear en busca de `*/SKILL.md` (actualmente
  `.agentic/skills`, `.claude/skills`, `.opencode/skills`).

### Cómo se construye la lista de archivos gestionados

`build_managed_files()` combina:

1. `managed_files` del manifest (lista explícita).
2. Los `*/SKILL.md` descubiertos por `discover_managed_skill_files()` en cada
   raíz de `managed_skill_roots`.

El resultado se ordena. Estas son las rutas que `agentic-sync` instala o
actualiza en el target.

`discover_core_skills()` lista las Core Skills escaneando
`.agentic/skills/*/SKILL.md` (solo nombres de directorio).

## Lockfile (`.agentic.lock.json`) — propósito dual

El framework utiliza `.agentic.lock.json` para dos propósitos diferentes.

### En el repositorio framework

El lockfile rastrea el estado de revisión de documentación.

```json
{
  "documentation": {
    "last_reviewed_commit": "<git-sha>",
    "last_reviewed_at": "<ISO-8601 timestamp>"
  }
}
```

Esta información es usada por `docs-update` para determinar qué commits quedan
por revisar.

### En repositorios consumidores

El lockfile registra el estado instalado del framework además de la información
de revisión de documentación. Tras `--apply`, `apply_plan()` actualiza
únicamente las claves de su propiedad y conserva cualquier otra clave de nivel
superior escrita por otros componentes:

Claves gestionadas por `agentic-sync`:

```json
{
  "framework_version": "0.1.0",
  "installed_at": "<ISO-8601>",
  "source": "<framework root path>",
  "managed_core_skills": ["commit-work", "docs-init", "docs-init-full", "docs-update"],
  "managed_files": {
    "<ruta>": { "sha256": "<hash>" }
  }
}
```

Claves externas conservadas (no gestionadas por sync): `documentation` y
cualquier otra clave de nivel superior que exista previamente. `agentic-sync`
no asume cuáles pueden ser esas claves; las preserva intactas.

Los contenidos típicos incluyen:

- versión del framework instalada;
- archivos gestionados (con sus hashes SHA-256);
- core skills instaladas;
- metadatos de revisión de documentación.

El hash guardado por archivo permite distinguir, en una próxima ejecución, un
`UPDATE` seguro (el destino coincide con el hash del lockfile) de un `CONFLICT`
genuino (el destino fue modificado de forma no rastreada).

El formato exacto puede evolucionar con futuras versiones del framework.

### Propiedades de escritura del lockfile

`apply_plan()` escribe `.agentic.lock.json` de forma segura:

- **Conservación de claves externas**: parte del lockfile existente y actualiza
  solo las claves gestionadas. Nunca reconstruye el fichero desde cero.
- **Escritura atómica**: serializa el JSON completo, lo escribe en un fichero
  temporal `.agentic.lock.json.tmp` en el mismo directorio y lo reemplaza con
  `os.replace` únicamente tras generar correctamente el JSON. Así no queda un
  lockfile parcialmente escrito si el proceso falla a mitad.
- **Lockfile inválido**: si `.agentic.lock.json` existe pero no es JSON válido o
  su raíz no es un objeto, `load_target_lockfile()` lanza un `ValueError` con un
  mensaje claro indicando el problema. El script termina con código de salida 1
  **sin sobrescribir** el fichero, para que pueda corregirse manualmente.

## Resolución de conflictos

- En `--apply` sin `--force`, los `CONFLICT` se dejan intactos y se conserva el
  hash del lockfile anterior para ese archivo (si existía).
- Con `--force`, los `CONFLICT` se sobrescriben con la versión del framework y se
  actualiza el hash del lockfile.
- Los `MISSING` (fuente inexistente en el framework) no se pueden instalar; se
  recomienda hacer `git pull` en el repositorio framework.

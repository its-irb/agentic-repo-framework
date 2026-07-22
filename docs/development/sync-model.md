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
  },
  "framework_remote_url": "<URL canónica del remoto origin del framework>",
  "framework_branch": "<rama actualmente checked out en el framework>",
  "framework_commit": "<SHA completo de HEAD del framework>"
}
```

Claves externas conservadas (no gestionadas por sync): `documentation` y
cualquier otra clave de nivel superior que exista previamente. `agentic-sync`
no asume cuáles pueden ser esas claves; las preserva intactas.

Los contenidos típicos incluyen:

- versión del framework instalada;
- archivos gestionados (con sus hashes SHA-256);
- core skills instaladas;
- trazabilidad del origen del framework (URL, rama y commit aplicados);
- metadatos de revisión de documentación.

El hash guardado por archivo permite distinguir, en una próxima ejecución, un
`UPDATE` seguro (el destino coincide con el hash del lockfile) de un `CONFLICT`
genuino (el destino fue modificado de forma no rastreada).

El formato exacto puede evolucionar con futuras versiones del framework.

### Trazabilidad del origen

`framework_remote_url`, `framework_branch` y `framework_commit` describen el
origen y la revisión exacta del framework aplicado en el **último `--apply`
completado correctamente**. Se obtienen del repositorio git local del framework
mediante `resolve_framework_origin()`:

| Clave | Cómo se obtiene |
|-------|-----------------|
| `framework_remote_url` | URL canónica de GitHub, resuelta a partir de la URL configurada en `origin` (ver debajo). |
| `framework_branch` | Rama actualmente checked out: `git symbolic-ref --short HEAD`. |
| `framework_commit` | SHA completo de `HEAD`: `git rev-parse --verify HEAD`. |

#### Resolución de `framework_remote_url`

La URL configurada localmente en `origin` (`git remote get-url origin`) es solo
el **punto de partida**, no el valor final: ese comando devuelve la URL
almacenada en la configuración del clon y **no** refleja una transferencia del
repositorio en GitHub (la URL antigua sigue configurada aunque GitHub redirija a
la nueva). Por eso `resolve_framework_origin()` hace:

1. `git remote get-url origin` → URL configurada (SSH o HTTPS).
2. `_parse_github_remote(url)` valida que es un remoto GitHub soportado:
   - SSH scp-like: `git@github.com:owner/repo.git`
   - SSH explícito: `ssh://git@github.com/owner/repo.git`
   - HTTPS: `https://github.com/owner/repo[.git]`
   - Cualquier otro host (GitLab, self-hosted, etc.) o forma no reconocida se
     rechaza antes de cualquier llamada remota.
3. `_ssh_to_https(url)` convierte la URL a HTTPS si era SSH (el repositorio
   framework es público, así la consulta HTTPS funciona sin credenciales). Las
   URLs HTTPS se usan tal cual.
4. `_run_git_lsremote(https_url)` ejecuta `git ls-remote <url> HEAD` con
   `LC_ALL=C` y `GIT_TERMINAL_PROMPT=0` (sin `--quiet`). Git sigue las
   redirecciones HTTP de GitHub y, por cada una, emite en stderr una línea:
   `warning: redirecting to <URL>`.
5. `_resolve_github_canonical` extrae las URLs de redirección del stderr. Si hay
   varias, se queda con la **última** (destino final). Si no hay ninguna y
   `git ls-remote` termina correctamente, la URL canónica es la consultada.
6. `_normalize_github_https` valida y normaliza la URL final a
   `https://github.com/<owner>/<repo>.git` (acepta con/sin `.git` y con/sin
   `/` final).

El valor guardado es la URL git canónica **normalizada**:
`https://github.com/<owner>/<repo>.git`, independiente del transporte de
entrada (SSH o HTTPS). Esto la hace estable y comparable entre clones.

La resolución reutiliza el transporte HTTPS, la configuración TLS y las
credenciales de Git ya disponibles y operativas en la máquina. No se apoya en
el almacén de certificados del intérprete Python, por lo que funciona en
instalaciones donde ese bundle no está configurado (p. ej. Python de python.org
en macOS sin ejecutar `Install Certificates.command`). No requiere instalar
`certifi`, `truststore` ni ningún paquete adicional: Git ya es una dependencia
necesaria del framework. No se desactiva la verificación TLS en ningún caso.

No se depende de una API autenticada de GitHub. No se modifica el remoto
`origin` del clon local; el objetivo es registrar la URL canónica en el lock.

Propiedades:

- Se re-resuelve en **cada** sincronización correcta y sustituye a los valores
  anteriores. Así, tras una transferencia, el siguiente `--apply` correcto
  sustituye la URL antigua del lock por la ubicación nueva (aunque la URL
  configurada localmente siga siendo la antigua), y avanza al commit más
  reciente.
- Se escriben **solo** tras completar el `apply`; un fallo no registra el nuevo
  commit ni la nueva URL.
- Son compatibles con lockfiles antiguos que no contengan estos campos: un
  lock sin ellos se completa sin perder las claves externas existentes.

Esta información habilita futuras comprobaciones de actualización (p. ej.
comparar el commit registrado con el commit actual del remoto para avisar de
que el destino va desactualizado). Dichas comprobaciones **no** forman parte del
sync y no se implementan en esta versión; el registro de trazabilidad es lo
único que se añade ahora.

### Propiedades de escritura del lockfile

`apply_plan()` escribe `.agentic.lock.json` de forma segura:

- **Validación del lockfile y resolución del origen antes de tocar el target**:
  `apply_plan()` valida primero el lockfile existente con
  `load_target_lockfile()` (local, barato) y luego llama a
  `resolve_framework_origin()`. Resolver la URL canónica ejecuta
  `git ls-remote`, así que validar el lockfile antes evita llamadas remotas
  innecesarias cuando el lock está corrupto. Si el estado git del framework no
  permite obtener fiablemente la rama o el commit (HEAD detached, sin commits,
  sin `origin`), o el remoto no es una URL GitHub soportada, o `git ls-remote`
  falla (red, TLS, repositorio privado/inexistente), o la URL final no es una
  URL HTTPS válida de `github.com`, se lanza un `ValueError` con un mensaje
  claro y el `apply` aborta sin modificar el target. **No hay fallback** a la
  URL configurada localmente: si la canónica no puede verificarse, no se
  registra. Nunca se escriben datos inventados ni ambiguos, y el lock nunca
  queda marcado con un commit no aplicado. El CLI termina con código 1.
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

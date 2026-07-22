# Guía de sincronización

Cómo instalar y mantener Agentic Repo Framework en un repositorio consumidor
usando `bin/agentic-sync.py`.

## Comandos

```bash
python bin/agentic-sync.py --plan <target>            # previsualiza, no modifica
python bin/agentic-sync.py --apply <target>           # instala/actualiza (respeta conflictos)
python bin/agentic-sync.py --apply --force <target>   # sobrescribe conflictos
```

- `<target>` es la ruta del repositorio consumidor (por defecto `.`).
- Sintaxis canónica: la acción (`--plan`/`--apply`) **antes** de la ruta target.

## Antes de sincronizar

Comprueba que:

- El repositorio framework y el target son repositorios git.
- El target no es el propio repositorio framework (no se permite).

Si alguna comprobación falla, el script muestra un error y termina sin hacer
cambios.

## Paso a paso

### 1. Previsualiza la instalación

```bash
python bin/agentic-sync.py --plan ./mi-repo
```

`--plan` es de solo lectura. Muestra:

- la versión del framework y las rutas del framework root y del target;
- las Core Skills detectadas;
- cada archivo gestionado con su estado;
- un resumen con contadores.

Úsalo siempre antes de `--apply` para revisar qué va a pasar.

### 2. Instala o actualiza

```bash
python bin/agentic-sync.py --apply ./mi-repo
```

`--apply` instala los archivos nuevos (`INSTALL`) y actualiza los que tienen una
versión más reciente del framework (`UPDATE`). Los `CONFLICT` se dejan intactos.
Al terminar escribe el lockfile `.agentic.lock.json` en el target.

### 3. Fuerza conflictos (con cuidado)

```bash
python bin/agentic-sync.py --apply --force ./mi-repo
```

`--force` sobrescribe los archivos en `CONFLICT` con la versión del framework.
Úsalo solo cuando estés seguro de querer descartar los cambios locales del
target en esos archivos.

## Estados de un archivo

El script clasifica cada archivo gestionado comparando el framework, el target y
el lockfile del target:

| Estado | Significado | Qué hace `--apply` |
|--------|-------------|--------------------|
| `INSTALL` | No existe en el target. | Lo copia. |
| `UPDATE` | Difiere del framework pero coincide con el lockfile (cambio seguro). | Lo sobrescribe. |
| `SKIP` | Idéntico al framework. | Nada. |
| `CONFLICT` | Difiere del framework y del lockfile (cambio local no rastreado). | Lo deja intacto, salvo `--force`. |
| `MISSING` | No existe en el framework. | Lo omite. |
## El lockfile (`.agentic.lock.json`)

Tras `--apply`, el target recibe `.agentic.lock.json` con:

- la versión del framework instalada;
- la fecha de instalación;
- la ruta del framework origen;
- las Core Skills instaladas;
- los archivos gestionados con sus hashes SHA-256;
- la **trazabilidad del origen**: URL canónica del repositorio framework en
  GitHub, rama y commit del framework aplicados.

La trazabilidad representa el origen y la revisión exacta del framework usado
en el último `--apply` completado correctamente. La URL canónica se
**re-resuelve** en cada sincronización: la URL configurada localmente en
`origin` es solo el punto de partida; el script consulta la ubicación actual
en GitHub siguiendo sus redirecciones. Así, si el repositorio framework se ha
transferido (p. ej. de una cuenta a una organización) y GitHub redirige a la
nueva ubicación, el siguiente `--apply` correcto sustituye la URL antigua del
lock por la nueva, aunque la URL configurada localmente siga siendo la
antigua. La URL se guarda normalizada como
`https://github.com/<owner>/<repo>.git`.

Esto permitirá en el futuro comprobar si el repositorio destino va
desactualizado respecto al framework; esas comprobaciones no forman parte del
sync hoy.

El hash de cada archivo permite que, en la siguiente sincronización, el script
distinga un `UPDATE` seguro (el archivo local coincide con el hash registrado)
de un `CONFLICT` genuino (el archivo local fue modificado de forma no
rastreada).

El lockfile es compartido con otras herramientas (por ejemplo, las skills
`docs-init`, `docs-init-full` y `docs-update` guardan ahí su baseline documental
bajo la clave `documentation`). `agentic-sync` solo actualiza sus propias claves
y conserva el resto sin modificarlo.

No borres ni edites manualmente el lockfile si quieres conservar la detección
correcta de conflictos. Si el fichero existe pero está corrupto (JSON inválido
o no es un objeto), `agentic-sync` no lo sobrescribe: muestra un error claro y
termina para que lo corrijas a mano.

Si el repositorio framework está en un estado git no fiable (HEAD detached, sin
remoto `origin`, o sin commits), o el remoto `origin` no es una URL GitHub
soportada, o no se puede verificar la URL canónica (sin red, timeout, error
HTTP, o repo privado/inaccesible), `--apply` aborta antes de cambiar nada y
avisa claramente; no se inventa la trazabilidad ni se marca un commit no
aplicado. Verificar la URL canónica requiere red, así que `--apply` necesita
conectividad a GitHub.

## Qué se gestiona y qué no

**Gestiona** `agentic-sync`:

- Core Skills (`.agentic/skills/`).
- Wrappers de Core Skills (`.claude/skills/`, `.opencode/skills/`).
- `docs/documentation-methodology.md`.

**No gestiona** (no los toca nunca):

- Repo Skills ni Personal Skills del consumidor.
- La documentación específica del repositorio consumidor.
- Cualquier otro archivo del consumidor.

## Resolución de problemas

### Aparecen archivos en `CONFLICT`

Alguien modificó localmente un archivo gestionado de forma no rastreada.
Revisa los cambios locales. Si quieres conservarlos, no uses `--force`. Si
quieres alinearlos con el framework, usa `--force` (perderás los cambios locales
en esos archivos).

### Aparecen archivos en `MISSING`

El framework no encuentra el archivo fuente. Suele pasar si el repositorio
framework no está actualizado. Haz `git pull` en el repositorio framework y
reintenta.

### El target no se reconoce como git

Asegúrate de que el target tiene un directorio `.git`. Si no, inicialízalo con
`git init` antes de sincronizar.

### Quiero sincronizar contra el directorio actual

```bash
python bin/agentic-sync.py --apply .
```

El target por defecto es `.`.

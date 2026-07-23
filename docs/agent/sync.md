# Sincronización (agentes)

`bin/agentic-sync.py` instala y actualiza los componentes gestionados del
framework en repositorios consumidores.

## Comandos

```bash
python bin/agentic-sync.py --plan <target>            # previsualiza, no modifica
python bin/agentic-sync.py --apply <target>           # instala/actualiza (respeta conflictos)
python bin/agentic-sync.py --apply --force <target>   # sobrescribe conflictos
```

- `<target>` es la ruta del repositorio consumidor (por defecto `.`).
- Sintaxis canónica: la acción (`--plan`/`--apply`) **antes** de la ruta target.
- El framework root se resuelve como el abuelo del script (`bin/` → raíz).

## Requisitos

- El framework root y el target deben ser repositorios git.
- El target no puede ser el propio repositorio framework.

## Estados de un fichero gestionado

`file_status()` clasifica cada fichero comparando fuente (framework), destino
(target) y hash del lockfile del target:

| Estado | Significado | Acción en `--apply` |
|--------|-------------|---------------------|
| `MISSING` | No existe en el framework. | Se omite. |
| `INSTALL` | Existe en framework, no en target. | Se copia. |
| `SKIP` | Source y destino idénticos (mismo SHA-256). | Nada. |
| `UPDATE` | Destino difiere de source pero coincide con el hash del lockfile. | Se sobrescribe (cambio seguro). |
| `CONFLICT` | Destino difiere de source y del hash del lockfile. | Se deja intacto, salvo `--force`. |

## Archivos gestionados

Definidos por el manifest `.agentic-framework.json`:

- `managed_files`: lista explícita. Actualmente:
  `docs/documentation-methodology.md`,
  `.agentic/tools/check-framework-updates.py` y
  `.opencode/plugins/agentic-update-check.js`.
- `managed_skill_roots`: raíces a escanear en busca de `*/SKILL.md`. Actualmente:
  `.agentic/skills`, `.claude/skills`, `.opencode/skills`.

La lista final gestionada = `managed_files` + los `*/SKILL.md` descubiertos en
cada raíz, ordenada.

`agentic-sync` **solo** gestiona Core Skills, sus wrappers,
`docs/documentation-methodology.md`, la herramienta de comprobación
`.agentic/tools/check-framework-updates.py` y el plugin de OpenCode
`.opencode/plugins/agentic-update-check.js`. No modifica Repo Skills, Personal
Skills ni la documentación específica del consumidor.

## Manifest

`.agentic-framework.json` (en el framework root):

```json
{
  "framework_version": "0.1.1",
  "managed_files": [
    "docs/documentation-methodology.md",
    ".agentic/tools/check-framework-updates.py",
    ".opencode/plugins/agentic-update-check.js"
  ],
  "managed_skill_roots": [".agentic/skills", ".claude/skills", ".opencode/skills"]
}
```

- `discover_core_skills()` escanea `.agentic/skills/*/SKILL.md` para listar las
  Core Skills.
- `discover_managed_skill_files()` recorre cada raíz con `glob("*/SKILL.md")`.

## Lockfile (`.agentic.lock.json`) — propósito dual

- **En este repositorio framework**: rastrea el baseline de revisión documental.

  ```json
  {
    "documentation": {
      "last_reviewed_commit": "<git-sha>",
      "last_reviewed_at": "<ISO-8601>"
    }
  }
  ```

  Usado por `docs-update` para saber qué commits quedan por revisar.

- **En repos consumidores**: registra el estado instalado del framework además
  de la revisión documental. Tras `--apply` se escribe con:
  `framework_version`, `installed_at`, `source`, `managed_core_skills`,
  `managed_files` (dict de ruta → `{sha256}`), y la trazabilidad del origen:
  `framework_remote_url`, `framework_branch`, `framework_commit`.

`agentic-sync` solo gestiona esas ocho claves. Cualquier otra clave de nivel
superior presente en el lockfile (p. ej. `documentation`, escrita por
`docs-init`/`docs-init-full`/`docs-update`) se conserva intacta entre
sincronizaciones; sync no asume cuáles pueden ser esas claves externas.

## Trazabilidad del origen

`framework_remote_url`, `framework_branch` y `framework_commit` representan el
origen y la revisión exacta del framework aplicado en el **último `--apply`
completado correctamente**. Se obtienen del repositorio git local del framework:

- `framework_remote_url`: **URL canónica** del repositorio en GitHub,
  normalizada como `https://github.com/<owner>/<repo>.git`. La URL configurada
  localmente en `origin` (`git remote get-url origin`) es solo el **punto de
  partida**: se convierte a HTTPS (si era SSH) y se ejecuta `git ls-remote`
  contra ella. Git sigue las redirecciones HTTP de GitHub y emite
  `warning: redirecting to <URL>`; esa URL final se registra. Así, si el
  repositorio se ha transferido y GitHub redirige de la ubicación antigua a la
  nueva, el lock registra la **nueva**. Se re-resuelve en cada sincronización y
  sustituye al valor anterior. Solo se soportan remotos GitHub (SSH o HTTPS
  sobre `github.com`).
- `framework_branch`: rama actualmente checked out (`git symbolic-ref --short
  HEAD`).
- `framework_commit`: SHA completo de `HEAD` (`git rev-parse HEAD`).

Estos datos permiten conocer la procedencia exacta de la sincronización y
comprobar si un repositorio destino está alineado con el estado actual del
framework. Las comprobaciones remotas de actualización no forman parte del
sync; esta información las habilita a futuro.

### Origen no fiable

Si alguno de los tres datos no puede determinarse de forma fiable, `apply_plan`
aborta **antes de tocar el target**: lanza un `ValueError` con un mensaje claro,
no copia ningún archivo y no reescribe el lockfile. Así nunca se escriben datos
inventados ni ambiguos, y el lock nunca queda marcado con un commit no
aplicado. El CLI termina con código 1. Esto cubre:

- HEAD detached, repositorio sin commits, o sin remoto `origin`.
- Remoto `origin` que no es una URL GitHub soportada (SSH/HTTPS sobre
  `github.com`).
- `git ls-remote` falla (red, TLS, repositorio privado/inexistente), o la URL
  final redirigida no es una URL HTTPS válida de `github.com`. No hay fallback
  a la URL configurada localmente: si no puede verificarse, no se registra.

Si el lockfile existe pero no es JSON válido o su raíz no es un objeto, sync
termina con código 1 **sin sobrescribirlo** (mensaje claro en stderr) para que
pueda corregirse manualmente. La escritura es atómica: se genera el JSON
completo en un `.tmp` y se reemplaza el original solo tras éxito.

El formato del lockfile de consumidor puede evolucionar con futuras versiones.

## Reglas de sync

- Solo instala/actualiza Core Skills.
- Nunca sobrescribe cambios locales sin mostrar previamente el estado (usa
  `--plan` para inspeccionar).
- `--force` sobrescribe conflictos con la versión del framework; úsalo con
  cuidado.

## Comprobación de actualizaciones (solo avisa)

OpenCode avisa al usuario cuando el repositorio destino no está sincronizado con
el último commit de la rama del framework registrada en `.agentic.lock.json`.
**Solo avisa; nunca sincroniza ni modifica el repositorio.**

### Disparador: `session.created`

- El disparador es **únicamente** el evento `session.created`. No hay
  comprobación durante la inicialización del plugin ni otros eventos.
- OpenCode materializa la sesión (y emite `session.created`) cuando el usuario
  envía el primer mensaje. Se acepta deliberadamente ese momento de
  comprobación: la menor inmediatez no justifica un plugin TUI.
- Las **sesiones hijas y subagentes** se ignoran: una sesión con `parentID`
  (campo oficial del SDK) no dispara comprobación. Solo las sesiones principales
  la disparan.

### Limitación horaria

- Como mucho **una comprobación remota por hora** por instancia cargada del
  plugin y por repositorio.
- `lastCheckAt` registra cuándo **comenzó** el último intento (éxito o fallo),
  no solo cuándo terminó correctamente. Así un fallo de red no provoca un nuevo
  intento con cada sesión creada.
- Crear muchas sesiones en la misma hora no consulta GitHub repetidamente.

### Limitación de avisos

- `UP_TO_DATE` y `SOURCE_REPO_SKIPPED` son silenciosos.
- `UPDATE_AVAILABLE`: la identidad del aviso es `remote_commit`.
  - Se notifica cuando nunca se ha notificado, o cuando `remote_commit` difiere
    del último notificado, o cuando han pasado **24 h** desde el último aviso
    para el mismo commit.
  - El mismo commit **no** vuelve a avisar antes de 24 h.
  - Un commit remoto **nuevo** puede notificarse en la siguiente comprobación
    horaria aunque no hayan pasado 24 h desde el aviso anterior.
- Diagnósticos (`LOCK_MISSING`, `LOCK_INCOMPLETE`, `LOCK_INVALID`,
  `REMOTE_BRANCH_MISSING`, `GIT_OR_NETWORK_ERROR`, y el error de ejecución de
  la herramienta `TOOL_EXECUTION_ERROR`): cada clave conserva
  **independientemente** su propio instante de último aviso (un `Map` en
  memoria). Alternar entre diagnósticos no reinicia la limitación de los
  anteriores. Ninguno se repite antes de 24 h.

### Estado solo en memoria

Todo el estado vive en memoria dentro de la instancia del plugin:
`lastCheckAt`, `checkInFlight`, `lastNotifiedCommit`, `lastNotificationAt` y el
`Map` de diagnósticos. **No hay persistencia en disco.** Reiniciar OpenCode
reinicia los límites: la primera sesión principal materializada puede volver a
comprobar y a avisar.

### Concurrencia

`checkInFlight` garantiza una sola comprobación en vuelo. Se establece
sincrónicamente antes de lanzar la herramienta y se limpia con `finally`, de
modo que dos sesiones casi simultáneas (o una principal y un subagente durante
la misma comprobación) lanzan a lo sumo una herramienta, y una excepción nunca
deja el estado bloqueado. El manejador es *fire-and-forget*: no espera a la
comprobación, así la sesión no se retrasa.

### Por qué no hay plugin TUI

Se descartó el plugin TUI para no crear ni gestionar `.opencode/tui.json`, no
editar configuración compartida de OpenCode y no introducir un segundo tipo de
plugin ni comprobaciones durante la inicialización. Si OpenCode incorpora en el
futuro un evento de inicio más adecuado, podrá sustituirse `session.created`.

### Herramienta común

Usa los datos registrados por el último `agentic-sync.py --apply`
(`framework_remote_url`, `framework_branch`, `framework_commit`).
- El repositorio fuente del framework se excluye automáticamente (detectado por
  `.agentic-framework.json`): no avisa.
- Consulta el remoto con `git ls-remote` (única dependencia: Git). No usa
  `urllib`/`requests`/`curl`/`certifi`.

La lógica vive en la herramienta común
`.agentic/tools/check-framework-updates.py` (agnóstica del arnés). El plugin
`.opencode/plugins/agentic-update-check.js` solo la invoca, interpreta el
resultado y aplica la limitación de avisos. **No duplica la lógica de Git, lock
ni comparación de commits**, y no modifica la herramienta Python.

### Estados del lock

La herramienta distingue tres estados distintos del lockfile:

- `LOCK_MISSING`: `.agentic.lock.json` **no existe**. La instalación está
  incompleta.
- `LOCK_INCOMPLETE`: el fichero existe pero le falta algún campo de
  trazabilidad (incluye un lock `{}` vacío). Hay que sincronizar una vez para
  registrar la procedencia.
- `LOCK_INVALID`: el fichero existe pero el JSON es inválido, la raíz no es un
  objeto, o un campo de trazabilidad tiene tipo incorrecto o no es un SHA
  completo válido.

### Flujo manual de actualización

Cuando hay una actualización disponible o el lock está incompleto, el aviso
indica el flujo manual actual:

1. Ir al clon local del Agentic Framework y actualizarlo con
   `git pull --ff-only`.
2. Desde ese clon actualizado, ejecutar
   `bin/agentic-sync.py --apply <repositorio-destino>`.

Si el lock incluye `source` (la ruta del clon usado en el último `apply`), el
aviso la muestra como ayuda informativa para localizar ese clon. No es un origen
canónico ni de confianza; es solo una pista.

En el futuro este flujo podrá cambiar cuando la sincronización se haga
directamente desde GitHub.

### Errores de ejecución de Git

Si `git` no está instalado, no se encuentra en `PATH`, o falla su ejecución
(incluido timeout), la herramienta lo convierte en el estado controlado
`GIT_OR_NETWORK_ERROR` (código 7). Nunca se produce un traceback. La sesión de
OpenCode continúa normalmente.

### Estados y códigos de retorno

| code | status | Aviso en OpenCode |
|------|--------|-------------------|
| 0 | `UP_TO_DATE` | silencio |
| 1 | `UPDATE_AVAILABLE` | aviso con commits cortos, rama y flujo `git pull --ff-only` + `python3 bin/agentic-sync.py --apply` (mismo commit: como mucho cada 24 h; commit nuevo: en la siguiente comprobación horaria) |
| 2 | `SOURCE_REPO_SKIPPED` | silencio |
| 3 | `LOCK_MISSING` | aviso: falta el lock, flujo manual completo (como mucho cada 24 h por clave) |
| 4 | `LOCK_INCOMPLETE` | aviso: falta trazabilidad, flujo manual completo (como mucho cada 24 h por clave) |
| 5 | `LOCK_INVALID` | aviso breve: no se pudo comprobar (como mucho cada 24 h por clave) |
| 6 | `REMOTE_BRANCH_MISSING` | aviso breve: no se pudo comprobar (como mucho cada 24 h por clave) |
| 7 | `GIT_OR_NETWORK_ERROR` | aviso breve: no se pudo comprobar (como mucho cada 24 h por clave) |

Ante fallos de red, Git o autenticación la sesión continúa normalmente; solo
muestra una advertencia breve. Los avisos de diagnóstico (códigos 3-7 y errores
de ejecución de la herramienta) se limitan a uno por clave cada 24 h en memoria,
para que no se repitan al crear sesiones.

### Ejecución manual (depuración)

```bash
python3 .agentic/tools/check-framework-updates.py --root <repo>            # JSON
python3 .agentic/tools/check-framework-updates.py --root <repo> --human     # legible
```

El código de salida coincide con la columna `code`.

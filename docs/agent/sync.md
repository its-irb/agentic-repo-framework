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
  `docs/documentation-methodology.md`.
- `managed_skill_roots`: raíces a escanear en busca de `*/SKILL.md`. Actualmente:
  `.agentic/skills`, `.claude/skills`, `.opencode/skills`.

La lista final gestionada = `managed_files` + los `*/SKILL.md` descubiertos en
cada raíz, ordenada.

`agentic-sync` **solo** gestiona Core Skills, sus wrappers y
`docs/documentation-methodology.md`. No modifica Repo Skills, Personal Skills ni
la documentación específica del consumidor.

## Manifest

`.agentic-framework.json` (en el framework root):

```json
{
  "framework_version": "0.1.0",
  "managed_files": ["docs/documentation-methodology.md"],
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

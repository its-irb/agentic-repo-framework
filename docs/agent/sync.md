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
  `managed_files` (dict de ruta → `{sha256}`).

`agentic-sync` solo gestiona esas cinco claves. Cualquier otra clave de nivel
superior presente en el lockfile (p. ej. `documentation`, escrita por
`docs-init`/`docs-update`) se conserva intacta entre sincronizaciones; sync no
asume cuáles pueden ser esas claves externas.

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

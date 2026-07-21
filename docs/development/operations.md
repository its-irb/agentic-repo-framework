# Operaciones

## Preparación del entorno

Requisitos:

- Git (el framework y los targets deben ser repositorios git).
- Python 3 (para ejecutar `bin/agentic-sync.py`). El script usa solo la
  biblioteca estándar; no requiere instalar dependencias.
- Uno o varios arneses soportados (Claude Code, OpenCode) para probar skills.

No hay `setup.py`, `pyproject.toml` ni dependencias de terceros. El framework es
un conjunto de ficheros de convención más un único script Python.

Clona el repositorio y ejecuta directamente desde la raíz:

```bash
git clone <framework-repo>
cd agentic-repo-framework
python bin/agentic-sync.py --plan <target>
```

## Añadir una nueva skill core

1. Crea la implementación común: `.agentic/skills/<nombre>/SKILL.md`.
2. Crea el wrapper para Claude Code: `.claude/skills/<nombre>/SKILL.md`.
3. Crea el wrapper para OpenCode: `.opencode/skills/<nombre>/SKILL.md`.
4. Verifica que `/<nombre>` funciona en ambos arneses.

Los wrappers no deben contener lógica de negocio. Ver
[skills-system.md](skills-system.md) para el contenido esperado de un wrapper.

Como el descubrimiento de skills en `agentic-sync` escanea
`.agentic/skills/*/SKILL.md`, crear el directorio con su `SKILL.md` basta para
que la skill quede gestionada como Core Skill.

## Añadir un wrapper para un arnés nuevo

1. Crea la estructura `<harness>/skills/<skill>/SKILL.md` con un fichero que
   redirija a la implementación común.
2. No dupliques lógica.
3. Para que `agentic-sync` lo gestione, añade la raíz del arnés (p. ej.
   `<harness>/skills`) a `managed_skill_roots` en `.agentic-framework.json`.

## Sincronizar el framework a un repositorio consumidor

```bash
python bin/agentic-sync.py --plan <target>
python bin/agentic-sync.py --apply <target>
python bin/agentic-sync.py --apply --force <target>
```

- `--plan` muestra lo que se instalaría sin modificar el target.
- `--apply` instala o actualiza archivos, dejando los conflictos intactos.
- `--force` sobrescribe los conflictos con la versión del framework.

La sintaxis canónica coloca la acción (`--plan` o `--apply`) antes de la ruta
del target. Ver [sync-model.md](sync-model.md) para el modelo completo, los
estados de fichero y el lockfile.

Validación previa: tanto el framework root como el target deben ser
repositorios git, y el target no puede ser el propio repositorio framework.

## Ejecución y depuración del sync

- `--plan` es de solo lectura: úsalo para inspeccionar el estado sin riesgo.
- La salida muestra cada archivo con su estado (`INSTALL`, `UPDATE`, `SKIP`,
  `CONFLICT`, `MISSING`) y un resumen con contadores.
- Si aparecen `CONFLICT`, revisa los cambios locales del target antes de usar
  `--force`.
- Si aparecen `MISSING`, haz `git pull` en el repositorio framework para
  asegurarte de tener la última versión.

No hay suite de tests automatizada del script. Los fixtures de test
(`.agentic/test-skills/`, `.agentic/test-docs/` y sus espejos en `.claude/` y
`.opencode/`) sirven para verificar manualmente la resolución de wrappers en los
arneses.

## Actualizar documentación

Cuando un cambio de código afecta a la arquitectura, las interfaces, la
operación, el flujo de desarrollo o el comportamiento visible, actualiza el
conocimiento correspondiente en las tres capas durante la misma sesión:

- `docs/agent/`
- `docs/development/`
- `docs/user/`
- `README.md` raíz.

Sigue los principios de `docs/documentation-methodology.md`. La skill
`docs-update` automatiza la revisión incremental desde el último commit
documentado; `docs-init` crea la estructura documental básica (directorios y
README mínimos); `docs-init-full` realiza la generación o adaptación integral
(útil al incorporar el repositorio al modelo de tres capas o cuando se
solicite documentación exhaustiva).

`docs-update` también puede invocarse con **alcance explícito** sobre un área
parcial (fichero, módulo, flujo, funcionalidad, etc.) para actualizar,
completar o crear su documentación sin revisar áreas no relacionadas. Esta
forma de uso permite a un humano revisar propuestas exhaustivas por partes sin
cargar demasiados cambios a la vez, manteniendo el flujo de propuesta y
confirmación.

El baseline de revisión documental se registra en `.agentic.lock.json` (campo
`documentation.last_reviewed_commit`).

## Mantenimiento del manifest

`.agentic-framework.json` declara la versión del framework, los archivos
gestionados explícitos (`managed_files`) y las raíces de skills
(`managed_skill_roots`). Modifícalo cuando:

- cambie la versión del framework;
- se añada un nuevo arnés soportado (nueva raíz en `managed_skill_roots`);
- se añada o elimine un archivo gestionado explícito (distinto de skills).

`docs/documentation-methodology.md` es un archivo gestionado explícito porque es
parte del contrato común del framework; no lo elimines del manifest.

## Despliegue y operación

El framework no se despliega como servicio. Su "despliegue" es la sincronización
a repos consumidores mediante `agentic-sync`. No hay runtime, servidor ni
proceso demonio. La operación se reduce a:

1. Mantener las skills y wrappers en el repositorio framework.
2. Sincronizar a consumidores con `agentic-sync --apply`.
3. Mantener la documentación coherente en las tres capas.

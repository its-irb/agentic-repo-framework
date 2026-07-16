# Documentación para agentes

Capa compacta y modular para que un agente de coding localice y modifique este
repositorio con seguridad, sin cargar documentación innecesaria ni depender de
`docs/development/` para el trabajo habitual.

## Cómo usar esta capa

Carga solo el módulo relacionado con tu tarea. Cada documento es autosuficiente
dentro de su ámbito.

## Módulos

- [architecture.md](architecture.md) — propósito, componentes, rutas relevantes,
  interfaces, invariantes y convenciones del framework.
- [skills.md](skills.md) — convención de invocación de skills, skills core
  disponibles y cómo añadir nuevas.
- [sync.md](sync.md) — `bin/agentic-sync.py`: comandos, estados de fichero,
  manifest, lockfile y archivos gestionados.

## Metodología

Las reglas de mantenimiento documental viven en
`docs/documentation-methodology.md` (archivo gestionado por el framework; no
modificar mediante sync). Cónsultala solo si la tarea toca documentación.

Para contexto técnico completo (intención, flujos detallados, mantenimiento y
extensión) acude a `docs/development/`. No debería hacer falta para el trabajo
habitual.

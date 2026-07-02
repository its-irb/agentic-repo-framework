# Adaptador Claude Code

Este adaptador explica cómo aplicar la metodología documental mínima usando Claude Code.

## Principio

`CLAUDE.md` debe ser mínimo. No debe importar toda la documentación con `@`.

Debe indicar qué documentos leer según la tarea.

## Uso recomendado

Para tareas de documentación:

- leer `docs/documentation-methodology.md` solo cuando se vaya a crear, reorganizar o revisar documentación;
- leer `docs/architecture.md` si la tarea afecta arquitectura;
- leer `docs/api.md` si la tarea afecta comunicación entre componentes;
- leer `docs/operations.md` si la tarea afecta despliegue u operación.

## Prohibido

- importar todos los documentos desde `CLAUDE.md`;
- duplicar documentación técnica dentro de `CLAUDE.md`;
- crear hooks o comandos que carguen documentación pesada por defecto.

## Futuro

Este adaptador podrá incluir:

- hooks de recordatorio documental;
- comandos slash;
- subagente de mantenimiento documental.
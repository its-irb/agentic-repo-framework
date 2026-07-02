# Adaptador OpenCode

Este adaptador explica cómo aplicar la metodología documental mínima usando OpenCode.

## Principio

La configuración de OpenCode debe ser mínima. No debe cargar toda la documentación al iniciar sesión.

Debe indicar qué documentos leer según la tarea.

## Uso recomendado

Para tareas de documentación:

- leer `docs/documentation-methodology.md` solo cuando se vaya a crear, reorganizar o revisar documentación;
- leer `docs/architecture.md` si la tarea afecta arquitectura;
- leer `docs/api.md` si la tarea afecta comunicación entre componentes;
- leer `docs/operations.md` si la tarea afecta despliegue u operación.

## Prohibido

- cargar toda la documentación al iniciar sesión;
- duplicar documentación técnica dentro de la configuración del arnés;
- crear plugins que inyecten documentación pesada por defecto.

## Futuro

Este adaptador podrá incluir:

- plugins TypeScript/JavaScript;
- comandos equivalentes a slash commands;
- recordatorios documentales;
- herramientas de mantenimiento documental.
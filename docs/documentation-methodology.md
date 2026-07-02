# Metodología de documentación mínima para agentes

## Objetivo

Mantener una documentación pequeña, útil y cargable bajo demanda por agentes de coding y desarrolladores humanos.

La documentación no debe intentar explicarlo todo. Debe guardar solo el conocimiento que no es evidente leyendo el código.

## Principios

1. Documentar solo lo útil:
   - arquitectura general;
   - APIs o interfaces entre partes;
   - despliegue y operación;
   - decisiones importantes si afectan al mantenimiento.

2. No duplicar código:
   si algo se entiende leyendo el código, no se documenta.

3. No cargar toda la documentación por defecto:
   los arneses deben indicar qué fichero leer según la tarea, no importar todos los documentos automáticamente.

4. Mantener pocos documentos:
   estructura recomendada para un repo pequeño:

   ```text
   docs/
   ├── README.md
   ├── architecture.md
   ├── api.md
   ├── operations.md
   └── notes/

5. Actualizar documentación junto con el código:
    si cambia la arquitectura, la API o el despliegue, se actualiza el documento correspondiente en la misma sesión.

## Uso por agentes

Los agentes deben:

* leer solo los documentos necesarios para la tarea;
* no importar documentación completa al iniciar sesión;
* avisar si un cambio de código requiere actualizar documentación;
* proponer cambios documentales, no inventarlos.

## Adaptadores

Cada arnés implementa esta metodología a su manera:

* Claude Code: adapters/claude-code/README.md
* OpenCode: adapters/opencode/README.md

La metodología común vive aquí. Los detalles de cada herramienta viven en su adaptador.
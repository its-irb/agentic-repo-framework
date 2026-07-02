---
name: docs-update
description: Revisa cambios actuales y actualiza documentación si procede.
---

# docs-update

Revisa si los cambios actuales del repositorio requieren actualizar documentación.

Primero lee:

docs/documentation-methodology.md

Después revisa los cambios actuales del repositorio usando el estado de git.

Evalúa si los cambios afectan a:

- arquitectura general;
- APIs o interfaces entre partes;
- despliegue u operación;
- decisiones importantes de mantenimiento.

Documentos habituales:

docs/README.md
docs/architecture.md
docs/api.md
docs/operations.md
docs/notes/

Reglas:

- No actualices documentación si el cambio no lo requiere.
- No inventes información.
- Si un cambio afecta documentación, actualiza el documento correspondiente o propón el cambio.
- Mantén los documentos cortos.
- Explica al final qué documentación se ha actualizado y por qué.

Resultado esperado:

- indicar si la documentación estaba al día;
- o actualizar/proponer cambios mínimos necesarios.

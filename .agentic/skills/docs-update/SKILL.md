---
name: docs-update
description: Revisa cambios desde el último commit documentado y actualiza documentación si procede.
---

# docs-update

Revisa si los cambios del repositorio desde el último commit documentado requieren actualizar documentación.

Primero lee:

docs/documentation-methodology.md

Después lee:

.agentic.lock.json

Si no existe `.agentic.lock.json`, o no contiene `documentation.last_reviewed_commit`:

- si no existe documentación básica, recomienda ejecutar `/docs-init`;
- si ya existe documentación, ayuda al usuario a elegir un commit base usando `git log --oneline -- docs`;
- no actualices documentación todavía sin baseline claro.

Si existe `documentation.last_reviewed_commit`:

1. Obtén el commit base desde `documentation.last_reviewed_commit`.

2. Revisa los cambios desde ese commit hasta `HEAD`:
   - `git log --oneline <base>..HEAD`
   - `git diff --name-status <base>..HEAD`
   - `git diff <base>..HEAD`

3. Deriva automáticamente qué áreas han cambiado a partir del diff y del árbol actual del repositorio. No uses una lista fija de rutas a revisar.

   Ten en cuenta especialmente:
   - ficheros añadidos;
   - ficheros borrados;
   - ficheros movidos;
   - ficheros modificados;
   - nuevas convenciones de directorios;
   - cambios en scripts ejecutables;
   - cambios en manifiestos o configuración;
   - cambios en skills o wrappers;
   - cambios en documentación existente.

4. Revisa la documentación existente y busca afirmaciones relacionadas con las áreas cambiadas.

5. Valida esas afirmaciones contra el estado actual del repositorio:
   - rutas mencionadas existen o han sido movidas;
   - listas de componentes coinciden con el árbol real;
   - comandos documentados coinciden con los scripts reales;
   - formatos descritos coinciden con los ficheros reales;
   - elementos movidos, renombrados o eliminados no siguen documentados como activos;
   - nuevas piezas relevantes del framework están documentadas si afectan al uso o mantenimiento.

6. Actualiza solo los documentos necesarios.

7. Antes de dar la documentación por válida, realiza una auditoría basada en evidencias contra el estado actual del repositorio.

   Para cada documento que consideres afectado por el rango revisado:

   1. Extrae las afirmaciones técnicas relevantes que contiene.
      Por ejemplo:
      - listas de skills, comandos, hooks o componentes;
      - rutas de ficheros o directorios;
      - formatos de lockfiles, manifests o configuración;
      - comandos de uso;
      - flujos de instalación, sincronización o actualización;
      - comportamiento descrito de scripts o herramientas.

   2. Para cada afirmación, identifica su fuente de verdad en el repositorio.
      Por ejemplo:
      - árbol actual de directorios;
      - contenido real de ficheros;
      - scripts ejecutables;
      - manifests;
      - lockfiles;
      - configuración;
      - salida de comandos de inspección.

   3. Comprueba la fuente de verdad antes de aceptar la afirmación como correcta.

   4. Si una afirmación no puede verificarse, no la des por válida:
      - corrígela si el estado real del repo es claro;
      - o márcala como pendiente de verificar si no puedes comprobarla.

   5. No concluyas que un documento está actualizado solo porque "parece coherente".
      Debes poder explicar qué evidencia del repositorio confirma las afirmaciones relevantes.

   La documentación debe describir el estado actual del proyecto, no solo cubrir el diff revisado.

8. Valida siempre el `README.md` raíz.

   - Comprueba que refleja las funcionalidades actuales del repositorio y que enlaza a la documentación relevante.
   - Si se añaden, eliminan o cambian funcionalidades visibles para usuarios, actualiza `README.md`.
   
   El `README.md` no se considera correcto solo por no contener afirmaciones falsas.

   Debe describir de forma útil el estado actual del proyecto:
   - qué es el proyecto;
   - qué problema resuelve;
   - qué funcionalidades principales tiene;
   - cómo se instala o sincroniza en un repo consumidor;
   - qué skills core existen;
   - cómo se usa el flujo básico;
   - dónde está la documentación detallada.

   Si el `README.md` es demasiado pobre, genérico o no refleja funcionalidades visibles para usuarios, actualízalo aunque no contenga errores factuales.

9. Al terminar correctamente, actualiza `.agentic.lock.json`:
   - `documentation.last_reviewed_commit` = commit actual de `HEAD`;
   - `documentation.last_reviewed_at` = fecha/hora actual real en formato ISO 8601.
   - Si no puedes obtener la fecha/hora real, deja `documentation.last_reviewed_at` en `null` y avisa.

Reglas:

- No inventes información.
- No actualices documentación si no hace falta.
- No modifiques código.
- Mantén los documentos cortos.
- No hardcodees en la revisión una lista fija de documentos o rutas; deriva lo afectado desde el diff, el árbol actual y las referencias existentes en la documentación.
- Si el diff muestra cambios relevantes no documentados, actualiza la documentación correspondiente.
- Explica al final:
  - qué rango de commits revisaste;
  - qué documentación se actualizó;
  - qué documentación no necesitó cambios;
  - si quedó algo pendiente de validar.
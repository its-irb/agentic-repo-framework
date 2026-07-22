---
name: commit-work
description: Revisa cambios, actualiza y valida las capas documentales si procede, y prepara un commit descriptivo.
---

# commit-work

Prepara un commit de trabajo con una descripción clara y completa.

## Proceso obligatorio

1. Revisa el estado del repositorio:

   - `git status --short`
   - `git diff --stat`
   - `git diff`

2. Determina el tipo de repositorio:

   - Si existe `.agentic-framework.json` en la raíz, considera que se está trabajando en el repositorio fuente del Agentic Framework.
   - Si no existe, considera que se está trabajando en un repositorio destino sincronizado mediante el framework.

3. Ejecuta siempre la lógica de `.agentic/skills/docs-update/SKILL.md` antes de preparar el commit, comunicándole explícitamente el tipo de repositorio detectado.

4. En el repositorio fuente del Agentic Framework:

   - La baseline documental debe representar el `HEAD` existente antes de crear el nuevo commit.
   - Es normal que, después del commit, `documentation.last_reviewed_commit` apunte al padre del nuevo `HEAD`.
   - No intentes hacer que la baseline apunte al commit que se está creando.
   - No propongas ciclos de `commit` y `amend` para actualizar la baseline.
   - No muestres opciones A/B/C para resolver esta diferencia esperada.
   - No modifiques ni valides como parte del flujo de commit los campos:
     - `framework_remote_url`;
     - `framework_branch`;
     - `framework_commit`.
   - Estos campos son responsabilidad exclusiva de `agentic-sync.py --apply`.

5. En un repositorio destino, aplica normalmente las reglas de baseline y trazabilidad definidas por `docs-update`.

6. Si `docs-update` indica que no existe un baseline documental o que el repositorio todavía no dispone de documentación inicial conforme a la metodología, ejecuta o propone el flujo de `.agentic/skills/docs-init/SKILL.md` antes de continuar.

7. Si `docs-update` o `docs-init` modifican documentación o estado documental, vuelve a revisar:

   - `git status --short`
   - `git diff --stat`
   - `git diff`

8. Comprueba que el resultado de la revisión documental incluye:

   - impacto en documentación para agentes;
   - impacto en documentación para desarrolladores;
   - impacto en documentación para usuarios;
   - validación del `README.md`;
   - validación de `AGENTS.md`, si existe;
   - comprobación de coherencia entre las capas afectadas;
   - comprobación de autosuficiencia de las capas afectadas;
   - pendientes de validación, si existen.

9. Propón el conjunto final de ficheros a incluir en el commit.

10. Propón un mensaje de commit con:

   - título corto;
   - cuerpo largo explicando qué cambió;
   - motivo del cambio;
   - impacto funcional;
   - impacto documental;
   - notas de validación realizadas.

11. Antes de ejecutar `git add` o `git commit`, pide confirmación explícita al usuario.

12. Si el usuario confirma:

   - ejecuta `git add` sobre los ficheros aprobados;
   - ejecuta `git commit` con el mensaje propuesto.

13. No hagas `git push` salvo que el usuario lo pida explícitamente.

14. Si el usuario pide push:

   - muestra primero la rama actual;
   - muestra el remote y el upstream configurados;
   - ejecuta `git push` solo tras confirmación explícita.

## Reglas

- No inventes cambios.
- No incluyas ficheros no revisados.
- No hagas commit si hay conflictos, secretos, binarios inesperados o cambios dudosos.
- No hagas commit si la documentación requerida no está actualizada, contiene contradicciones conocidas o alguna capa afectada ha quedado insuficiente.
- No modifiques documentación solo para producir cambios artificiales.
- Si el estado del repositorio no está claro, detente y pregunta.
- La presencia de `.agentic-framework.json` en la raíz es el criterio autoritativo para identificar el repositorio fuente.
- En el repositorio fuente, no trates como error que la baseline documental quede un commit por detrás después de crear el commit.
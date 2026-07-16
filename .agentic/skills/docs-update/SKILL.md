---
name: docs-update
description: Revisa los cambios desde el último commit documentado, actualiza la documentación afectada y verifica la coherencia entre README, agentes, desarrolladores y usuarios.
---

# docs-update

Revisa si los cambios del repositorio desde el último commit documentado requieren actualizar documentación.

Primero lee:

```text
docs/documentation-methodology.md
```

Después lee:

```text
.agentic/config.json
.agentic.lock.json
```

## Configuración inicial

Comprueba que `.agentic/config.json` existe y contiene una audiencia válida:

- `technical`;
- `general`.

Si falta el fichero o la audiencia:

- no continúes con la actualización normal;
- indica que el repositorio debe inicializarse o adaptarse;
- ejecuta o recomienda ejecutar la lógica de `.agentic/skills/docs-init/SKILL.md`.

## Baseline documental

Si no existe `.agentic.lock.json`, o no contiene `documentation.last_reviewed_commit`:

- si no existe documentación básica, recomienda ejecutar `/docs-init`;
- si ya existe documentación, ayuda al usuario a elegir un commit base usando `git log --oneline -- docs`;
- no actualices documentación todavía sin baseline claro.

Si existe `documentation.last_reviewed_commit`, continúa con el proceso obligatorio.

## Proceso obligatorio

1. Valida siempre el `README.md` raíz, aunque el rango de commits no parezca afectarlo.

   La validación del README no depende del diff y debe ejecutarse en cada invocación.

2. Obtén el commit base desde `documentation.last_reviewed_commit`.

3. Revisa los cambios desde ese commit hasta `HEAD`:

   - `git log --oneline <base>..HEAD`
   - `git diff --name-status <base>..HEAD`
   - `git diff <base>..HEAD`

4. Deriva automáticamente qué áreas han cambiado a partir del diff y del árbol actual del repositorio.

   No uses una lista fija de rutas a revisar.

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

5. Evalúa por separado el impacto en:

   - documentación para agentes;
   - documentación para desarrolladores;
   - documentación para usuarios;
   - `README.md`;
   - `AGENTS.md`, si existe.

   No es obligatorio modificar todos los niveles. Actualiza solo los afectados.

6. Revisa la documentación existente y busca afirmaciones relacionadas con las áreas cambiadas.

7. Valida esas afirmaciones contra el estado actual del repositorio:

   - las rutas mencionadas existen o reflejan correctamente los movimientos;
   - las listas de componentes coinciden con el árbol real;
   - los comandos documentados coinciden con los scripts reales;
   - los formatos descritos coinciden con los ficheros reales;
   - los elementos movidos, renombrados o eliminados no siguen documentados como activos;
   - las nuevas piezas relevantes están documentadas si afectan al uso o mantenimiento;
   - el comportamiento visible para usuarios coincide con la implementación actual.

8. Actualiza solo los documentos necesarios.

## Auditoría basada en evidencias

Antes de dar la documentación por válida, realiza una auditoría contra el estado actual del repositorio.

Para cada documento afectado por el rango revisado:

1. Extrae las afirmaciones técnicas o funcionales relevantes.

   Por ejemplo:

   - listas de skills, comandos, hooks o componentes;
   - rutas de ficheros o directorios;
   - formatos de lockfiles, manifests o configuración;
   - comandos de uso;
   - flujos de instalación, sincronización o actualización;
   - comportamiento de scripts, herramientas o funcionalidades;
   - capacidades y limitaciones visibles para usuarios.

2. Para cada afirmación, identifica su fuente de verdad.

   Por ejemplo:

   - árbol actual de directorios;
   - contenido real de ficheros;
   - scripts ejecutables;
   - manifests;
   - lockfiles;
   - configuración;
   - interfaces públicas;
   - salida de comandos de inspección.

3. Comprueba la fuente de verdad antes de aceptar la afirmación.

4. Si una afirmación no puede verificarse:

   - corrígela si el estado real del repositorio es claro;
   - o márcala como pendiente de verificar.

5. No concluyas que un documento está actualizado solo porque parece coherente.

   Debes poder explicar qué evidencia confirma las afirmaciones relevantes.

La documentación debe describir el estado actual del proyecto, no limitarse a cubrir el diff revisado.

## Coherencia entre niveles

Para los conceptos afectados por el cambio, busca referencias relacionadas en:

- `README.md`;
- `AGENTS.md`, si existe;
- `docs/agent/`;
- `docs/development/`;
- `docs/user/`;
- cualquier otra documentación existente que cumpla esas funciones.

Comprueba que:

- se usan nombres compatibles;
- se describe el mismo comportamiento;
- coinciden las capacidades y limitaciones;
- no hay rutas, comandos o instrucciones incompatibles;
- no se mantiene como actual algo eliminado o sustituido;
- el nivel de detalle y el lenguaje cambian según la audiencia, pero no los hechos.

Si detectas una contradicción:

1. determina el comportamiento real a partir del repositorio;
2. corrige todos los documentos afectados;
3. no des la documentación por válida mientras la contradicción permanezca.

## Validación obligatoria del README

El `README.md` raíz debe actuar como puerta de entrada útil y seguir las convenciones habituales para el tipo real de proyecto.

Deriva primero la superficie pública del repositorio.

Inspecciona, si existen:

- scripts ejecutables;
- comandos o herramientas CLI;
- skills, hooks, plugins, workflows o integraciones de agentes;
- manifests, lockfiles o ficheros de configuración relevantes;
- servicios, entrypoints, APIs o interfaces públicas;
- documentación existente;
- funcionalidades visibles para usuarios.

Comprueba que el README explica, cuando proceda:

1. qué es el proyecto;
2. qué problema resuelve;
3. para quién está pensado;
4. sus funcionalidades principales;
5. el flujo básico de uso;
6. el flujo básico de instalación, ejecución o sincronización;
7. los comandos, scripts, herramientas o puntos de entrada principales;
8. el estado o madurez del proyecto, si es relevante;
9. dónde encontrar la documentación detallada;
10. cómo contribuir, obtener soporte o consultar la licencia, cuando corresponda.

No marques un punto como no aplicable solo porque el README actual no lo mencione. Debes haber inspeccionado antes la superficie pública y comprobado que realmente no corresponde al proyecto.

Si existe una funcionalidad pública, comando, script, skill, servicio, API, workflow o mecanismo de instalación, el README debe mencionarlo de forma resumida cuando sea relevante para entender o empezar a usar el proyecto.

Si el README menciona algo que ya no existe, corrígelo.

Si es genérico, pobre, incompleto o no permite entender cómo empezar, actualízalo aunque no contenga afirmaciones falsas.

No conviertas el README en la documentación completa: debe presentar el proyecto, ofrecer un inicio útil y enlazar los documentos detallados.

## Actualización del baseline

Al terminar correctamente, actualiza `.agentic.lock.json`:

- `documentation.last_reviewed_commit` = commit actual de `HEAD`;
- `documentation.last_reviewed_at` = fecha y hora actual real en formato ISO 8601;
- si no puedes obtener la fecha y hora real, usa `null` y avisa.

## Reglas

- No inventes información.
- No actualices documentación si no hace falta.
- No modifiques código.
- Mantén compacta la documentación para agentes.
- En documentación para desarrolladores y usuarios, prioriza claridad y suficiencia sobre brevedad.
- No hardcodees una lista fija de documentos o rutas; deriva lo afectado desde el diff, el árbol actual y las referencias existentes.
- Si el diff muestra cambios relevantes no documentados, actualiza la documentación correspondiente.
- No des la revisión por terminada si existen contradicciones conocidas entre niveles documentales.

## Resultado

Explica al final:

- qué rango de commits revisaste;
- qué audiencia tiene el repositorio;
- qué impacto evaluaste en agentes, desarrolladores, usuarios, README y AGENTS;
- qué documentación se actualizó;
- qué documentación no necesitó cambios;
- qué evidencias principales utilizaste;
- si detectaste o resolviste contradicciones;
- si quedó algo pendiente de validar.
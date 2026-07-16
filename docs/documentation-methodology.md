# Metodología de documentación del repositorio

## Objetivo

Mantener una documentación actualizada, coherente y adaptada a sus distintas audiencias:

- agentes de coding;
- desarrolladores y mantenedores;
- usuarios del proyecto.

La documentación destinada a agentes debe seguir siendo pequeña, modular y cargable bajo demanda. La documentación destinada a desarrolladores y usuarios puede ser más extensa cuando sea necesario para comprender, mantener o utilizar correctamente el proyecto.

## Audiencia del repositorio

Cada repositorio debe declarar su audiencia en:

```text
.agentic/config.json
```

Valores admitidos:

- `technical`: repositorios destinados principalmente a desarrolladores, administradores, DevOps u otros usuarios técnicos;
- `general`: aplicaciones o servicios destinados a usuarios finales no especializados.

La audiencia determina principalmente el lenguaje, los conocimientos que pueden asumirse y la profundidad de la documentación de uso. No impone una estructura fija ni un número determinado de documentos.

Si falta esta configuración, `docs-init` debe solicitarla y adaptar la documentación existente a esta metodología.

## Niveles de documentación

La documentación se organiza conceptualmente en tres niveles.

### Documentación para agentes

Debe permitir que un agente comprenda y modifique el repositorio de forma selectiva sin cargar documentación innecesaria.

Debe ser:

- pequeña;
- modular;
- orientada a responsabilidades, arquitectura, interfaces, invariantes, convenciones y operación;
- cargable bajo demanda;
- centrada en el conocimiento necesario para localizar y modificar el código con seguridad.

No debe reproducir el código ni convertirse en un manual exhaustivo.

La ubicación recomendada es:

```text
docs/agent/
```

La estructura interna depende de las necesidades reales del proyecto.

### Documentación para desarrolladores

Debe permitir que un desarrollador comprenda el proyecto, su intención, su estructura y sus principales flujos sin tener que leer previamente todo el código.

Puede incluir, según proceda:

- arquitectura y responsabilidades;
- estructura del repositorio;
- flujos entre componentes;
- decisiones y restricciones relevantes;
- preparación del entorno;
- ejecución, pruebas y depuración;
- despliegue y operación;
- extensibilidad y mantenimiento.

No debe duplicar mecánicamente el código, pero sí explicar el contexto necesario para comprenderlo y modificarlo con seguridad.

La ubicación recomendada es:

```text
docs/development/
```

La estructura y extensión dependen de la complejidad del proyecto.

### Documentación para usuarios

Debe explicar cómo instalar, acceder, configurar y utilizar el proyecto, así como resolver los problemas habituales.

En repositorios con audiencia `technical`, puede asumir conocimientos técnicos razonables, pero debe seguir siendo suficiente y operativa.

En repositorios con audiencia `general`, debe:

- utilizar lenguaje comprensible para usuarios no especializados;
- evitar detalles internos innecesarios;
- describir tareas desde la perspectiva del producto;
- cubrir los primeros pasos, las funciones principales, la configuración visible, los errores frecuentes y la recuperación.

La ubicación recomendada es:

```text
docs/user/
```

La estructura y el número de documentos dependen de la superficie funcional del proyecto.

## Principios generales

1. Documentar según la audiencia y el propósito.

   La brevedad es prioritaria en la documentación para agentes. En la documentación para desarrolladores y usuarios, deben priorizarse la claridad, la suficiencia y la utilidad.

2. No imponer una estructura rígida.

   Cada proyecto debe tener únicamente los documentos que necesite. No existe una lista fija de nombres, directorios internos ni número de ficheros.

3. No duplicar mecánicamente el código.

   No documentar línea por línea aquello que el código expresa de forma evidente. Sí documentar intención, contexto, relaciones, flujos, decisiones, restricciones y procedimientos que sería costoso reconstruir leyendo el repositorio.

4. No cargar toda la documentación por defecto.

   Los agentes deben consultar solo los documentos necesarios para la tarea actual. Deben empezar por la documentación compacta de `docs/agent/` y profundizar en `docs/development/` o `docs/user/` cuando la tarea lo requiera.

5. Referenciar documentación mediante rutas normales del repositorio.

   Por ejemplo:

   ```text
   docs/agent/architecture.md
   docs/development/testing.md
   docs/user/getting-started.md
   ```

   No usar sintaxis específica de un arnés, como `@docs/...`, dentro de documentación o skills comunes.

6. Actualizar la documentación junto con el código.

   Si cambia la arquitectura, una interfaz, la operación, el flujo de desarrollo o el comportamiento visible para usuarios, debe actualizarse la documentación correspondiente en la misma sesión.

7. Reutilizar antes de crear.

   Al adaptar un repositorio existente, conservar la documentación útil, reclasificarla o ampliarla cuando sea necesario y crear únicamente lo que falte.

8. No inventar información.

   Toda afirmación debe poder justificarse con el estado actual del repositorio. Si algo no puede verificarse, debe marcarse como pendiente de validar.

## Coherencia documental

La documentación debe mantenerse como un conjunto coherente, no como documentos independientes.

Al crear o actualizar documentación:

1. Verificar las afirmaciones relevantes contra el código, la configuración, los scripts, los manifiestos, las interfaces y el comportamiento actual del repositorio.
2. Buscar referencias al mismo concepto, componente, comando, flujo o funcionalidad en:
   - `README.md`;
   - `AGENTS.md`, si existe;
   - `docs/agent/`;
   - `docs/development/`;
   - `docs/user/`.
3. Comprobar que todos los niveles:
   - utilizan nombres compatibles;
   - describen el mismo comportamiento;
   - reflejan las mismas capacidades y limitaciones;
   - no mantienen como activo algo eliminado o sustituido;
   - no ofrecen instrucciones incompatibles.
4. Adaptar el nivel de detalle y el lenguaje a cada audiencia sin cambiar los hechos.
5. Si dos documentos se contradicen, determinar el comportamiento real a partir del repositorio y corregir todos los documentos afectados.
6. No considerar la documentación actualizada mientras existan contradicciones conocidas entre sus distintos niveles.

Los niveles documentales pueden resumir, ampliar o adaptar el lenguaje, pero deben describir el mismo sistema.

## Uso por agentes

Los agentes deben:

- leer solo los documentos necesarios para la tarea;
- no cargar toda la documentación al iniciar la sesión;
- empezar por `docs/agent/` cuando necesiten contexto compacto;
- consultar `docs/development/` cuando necesiten comprender diseño, flujos o mantenimiento;
- consultar `docs/user/` cuando el cambio afecte al uso visible del producto;
- utilizar rutas normales del repositorio;
- avisar si un cambio de código requiere actualizar documentación;
- proponer o realizar cambios documentales basados en evidencias, sin inventarlos.

## Skills comunes

Las acciones reutilizables viven en:

```text
.agentic/skills/<skill>/SKILL.md
```

Cada arnés implementa un wrapper mínimo:

```text
.claude/skills/<skill>/SKILL.md
.opencode/skills/<skill>/SKILL.md
```

La lógica de cada skill vive una única vez en `.agentic/skills/`.

Los wrappers no deben contener lógica de negocio; únicamente deben invocar la implementación común.

## README principal

El `README.md` de la raíz es la puerta de entrada al proyecto y debe seguir convenciones habituales de la industria.

Debe permitir que una persona que no conoce el repositorio entienda:

- qué es el proyecto;
- qué problema resuelve;
- para quién está pensado;
- cuáles son sus funcionalidades principales;
- cómo instalarlo, ejecutarlo, sincronizarlo o empezar a utilizarlo;
- cuáles son sus puntos de entrada, comandos o flujos principales;
- cuál es su estado o madurez, cuando sea relevante;
- dónde encontrar la documentación detallada;
- cómo contribuir, obtener soporte o consultar la licencia, cuando proceda.

No debe duplicar toda la documentación interna. Debe presentar el proyecto, ofrecer un inicio mínimo útil y enlazar la documentación adecuada para usuarios y desarrolladores.

El contenido exacto debe adaptarse al tipo real de proyecto. No todos los repositorios necesitan las mismas secciones.

El `README.md` no se considera correcto solo por no contener afirmaciones falsas. Si es demasiado pobre, genérico, incompleto o no refleja funcionalidades visibles, debe actualizarse aunque no contenga errores factuales.
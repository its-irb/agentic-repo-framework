---
name: docs-init
description: Inicializa o adapta la documentación del repositorio a la metodología vigente, incluida la audiencia, la documentación para agentes, desarrolladores y usuarios, y el README principal.
---

# docs-init

Inicializa o adapta la documentación de este repositorio.

Primero lee:

```text
docs/documentation-methodology.md
```

Después inspecciona:

- `.agentic/config.json`, si existe;
- la documentación existente;
- `README.md`;
- `AGENTS.md`, si existe;
- el código, la configuración, los scripts, los manifiestos y la superficie pública del repositorio.

## Audiencia

Comprueba si `.agentic/config.json` contiene la audiencia del repositorio.

Los valores admitidos son:

- `technical`;
- `general`.

Si falta `.agentic/config.json` o no contiene la audiencia:

1. Explica brevemente la diferencia entre ambas opciones.
2. Pide al usuario que elija una.
3. Crea o actualiza `.agentic/config.json` conservando cualquier configuración existente.
4. No infieras ni fijes la audiencia sin confirmación del usuario.

La ausencia de audiencia indica que el repositorio todavía no ha sido inicializado o adaptado a la convención documental vigente.

## Inicialización o adaptación

Inspecciona la documentación existente antes de crear, mover o ampliar documentos.

Debes asegurar que el repositorio disponga, de acuerdo con sus necesidades reales, de:

- documentación compacta y modular para agentes;
- documentación técnica suficiente para desarrolladores;
- documentación de uso adaptada a la audiencia;
- un `README.md` adecuado como puerta de entrada.

Utiliza preferentemente estas ubicaciones:

```text
docs/agent/
docs/development/
docs/user/
```

No impongas nombres, subdirectorios ni un número fijo de documentos.

Si el repositorio ya contiene documentación:

- conserva todo el contenido útil;
- identifica a qué nivel pertenece cada documento;
- reutiliza, reorganiza, divide o amplía solo cuando sea necesario;
- crea únicamente la documentación que falte;
- actualiza referencias internas cuando cambien rutas;
- no regeneres toda la documentación desde cero.

En repositorios antiguos del framework, trata la documentación mínima existente como candidata a documentación para agentes, pero valida su propósito y contenido antes de reclasificarla.

En repositorios con documentación creada fuera del framework, respeta lo que ya sea útil y adapta solo lo necesario para cumplir la metodología.

Antes de sobrescribir, mover, dividir o renombrar documentación existente, presenta una propuesta breve y pide confirmación al usuario.

## Validación

Antes de dar la inicialización por terminada:

- verifica las afirmaciones relevantes contra el estado actual del repositorio;
- comprueba que `README.md`, `AGENTS.md` y los distintos niveles documentales no se contradicen;
- comprueba que las rutas y enlaces internos siguen siendo válidos;
- comprueba que no se ha perdido información útil;
- marca como pendiente cualquier información que no pueda verificarse.

Al finalizar correctamente:

- actualiza `.agentic.lock.json`;
- establece `documentation.last_reviewed_commit` al commit actual de `HEAD`;
- establece `documentation.last_reviewed_at` a la fecha y hora actual real en formato ISO 8601;
- si no puedes obtener la fecha y hora real, usa `null` y avisa.

## Reglas

- No inventes APIs, servicios, comandos, funcionalidades ni arquitectura.
- Mantén compacta la documentación para agentes.
- En documentación para desarrolladores y usuarios, prioriza claridad y suficiencia sobre brevedad.
- No borres documentación útil.
- No impongas una estructura rígida.
- No modifiques código.
- Si algo no está claro, márcalo como pendiente de verificar.

## Resultado esperado

Explica brevemente:

- la audiencia configurada;
- si el repositorio se inicializó o se adaptó;
- qué documentación se creó, reutilizó, reorganizó o amplió;
- qué cambios estructurales requieren confirmación;
- qué queda pendiente de validar.
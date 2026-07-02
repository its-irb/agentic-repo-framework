# Sistema de Skills

## Objetivo

El framework mantiene una única implementación de cada skill, independientemente del arnés utilizado (Claude Code u OpenCode).

La lógica común nunca se duplica.

## Estructura

```
.agentic/
└── skills/
    └── <skill>/
        └── SKILL.md      ← implementación común

.claude/
└── skills/
    └── <skill>/
        └── SKILL.md      ← wrapper Claude Code

.opencode/
└── skills/
    └── <skill>/
        └── SKILL.md      ← wrapper OpenCode
```

## Funcionamiento

Cuando el usuario ejecuta:

```
/<skill>
```

el arnés carga el wrapper correspondiente.

El wrapper únicamente redirige a la implementación común situada en:

```
.agentic/skills/<skill>/SKILL.md
```

Toda la lógica de la skill reside exclusivamente en ese documento.

## Principios

- Una única implementación por skill.
- Un wrapper por arnés soportado.
- Los wrappers no contienen lógica de negocio.
- La implementación común debe ser independiente del arnés siempre que sea posible.

## Añadir una nueva skill

1. Crear:

```
.agentic/skills/<nombre>/SKILL.md
```

2. Crear el wrapper para Claude Code:

```
.claude/skills/<nombre>/SKILL.md
```

3. Crear el wrapper para OpenCode:

```
.opencode/skills/<nombre>/SKILL.md
```

4. Verificar que `/nombre` funciona en ambos arneses.

## Cuándo modificar cada archivo

**Implementación común**

Modificar cuando cambia el comportamiento de la skill.

**Wrapper**

Modificar únicamente cuando cambie la forma en que un arnés invoca las skills.
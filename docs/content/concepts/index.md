# Concepts

These pages state how Supershelf behaves.

```mermaid
flowchart LR
  discover[Discover profiles] --> walk[Walk inputs]
  walk --> match[First matching rule]
  match --> facts[File facts]
  facts --> defaults[default_vars]
  defaults --> kindFile[Kind file]
  kindFile --> ruleVars[Rule vars]
  ruleVars --> overrides[First override]
```

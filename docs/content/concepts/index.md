# Concepts

These pages state how Supershelf behaves.

```mermaid
flowchart LR
  discover[Discover profiles] --> walk[Walk inputs]
  walk --> match[First matching rule]
  match --> facts[File facts]
  facts --> defaults[default_vars]
  defaults --> ruleVars[Rule vars]
  ruleVars --> kindFile[Kind file row]
  kindFile --> recorded[Record]
  recorded --> output[Output]
```

---
name: My Example
description: Cosa fa l'agente e quando usarlo
tools: ['read', 'search']
# handoffs:
#   - label: Implementa
#     agent: agent
#     prompt: Implementa il piano sopra.
#     send: false
# user-invocable: false   # nasconde l'agente dal menu (resta usabile come subagent)
---
Descrivi il ruolo dell'agente, cosa deve fare e cosa deve restituire.
Limita `tools` al minimo necessario (principio del minimo privilegio).

Copiare in `.github/agents/my-<nome>.agent.md`.

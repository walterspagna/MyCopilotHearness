---
name: my-example
description: Cosa fa il prompt
argument-hint: Cosa scrivere dopo il comando
# agent: agent        # ask | agent | plan | nome di un agente custom
# model: ...          # opzionale
# tools: ['read', 'search']
---
Testo del prompt. Input variabili: ${input:nome:segnaposto}. Selezione corrente: ${selection}.
Riferimento a file: [istruzioni](../instructions/my-example.instructions.md).

Copiare in `.github/prompts/my-<nome>.prompt.md`. Si lancia con `/my-example` in una sessione Local.

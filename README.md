# MyCopilotHearness

Harness Copilot **personale**: agenti, skill, instruction, prompt e hook solo per me. Non contiene standard di sviluppo, linee guida o regole del framework NET@SAAS: quelle stanno negli altri repo del workspace.

## Come viene caricato

VS Code cerca `.github/agents`, `.github/skills`, `.github/instructions`, `.github/prompts`, `.github/hooks`, `.github/copilot-instructions.md` e `AGENTS.md` nella radice di ogni cartella del workspace. Questa cartella è una radice del workspace multi-root, quindi i suoi strumenti sono disponibili insieme a quelli degli altri repo. Se la cartella non è nel workspace, non esistono.

Il repo git è separato (nessun push sul repo comune). Non aggiungere questa cartella a `NETAASSISTANT.code-workspace` (è tracciato nel repo comune): usa un `.code-workspace` personale fuori dai repo condivisi (i file `*.code-workspace` qui sono ignorati da git).

## Struttura

| Percorso | Contenuto | Caricato da Copilot |
|---|---|---|
| `AGENTS.md`, `.github/copilot-instructions.md` | Regole personali sempre attive (brevi) | Sì |
| `.github/agents/` | `my-*.agent.md` | Sì |
| `.github/skills/` | `my-*/SKILL.md` (nome cartella = campo `name`) | Sì |
| `.github/instructions/` | `my-*.instructions.md` | Sì |
| `.github/prompts/` | `my-*.prompt.md` (solo sessioni Local) | Sì |
| `.github/hooks/` | `my-*.json` | Sì (Preview) |
| `Templates/` | Modelli da copiare | No |
| `Sandbox/` | Prove usa e getta | No |

## Convenzioni

- Prefisso `my-` su tutto, per distinguere dagli strumenti del team (`EFO-*`, instruction dei repo).
- Instruction: niente `applyTo` generici (`**`, `**/*.cs`): varrebbero anche sul codice degli altri repo. Usare solo `description` (caricamento on demand) o pattern stretti.
- Skill: `name` solo minuscole, numeri e trattini, uguale al nome della cartella, max 64 caratteri.
- Nomi duplicati tra radici: per le skill vince la radice primaria del workspace; il prefisso `my-` evita il problema.
- Nessun segreto in questo repo (anche se privato).
- Le regole di dominio vanno nei repo di progetto, non qui.

## Aggiungere uno strumento

1. Copia il modello da `Templates/` nella cartella giusta di `.github/`.
2. Rinomina con prefisso `my-` e compila il frontmatter.
3. Nuova chat: verifica in *Chat: Open Customizations* che sia elencato; se non compare, `Developer: Reload Window`.
4. Per capire perché qualcosa non si carica: *Developer: Open Agent Debug Logs*.

## Primo test

Digita `/my-hello` nella chat (sessione Local): deve rispondere indicando da quale cartella è stato caricato.

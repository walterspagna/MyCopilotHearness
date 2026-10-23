// Hook di esempio (Preview): registra solo il nome del tool, mai argomenti o risultati.
// Copiare con my-example.hook.json in .github/hooks/. Richiede Node.js. Il file .log è ignorato da git.
// I hook sono codice eseguibile e agiscono su TUTTE le sessioni del workspace: provarli uno alla volta.
const fs = require('node:fs');
const path = require('node:path');

const event = JSON.parse(fs.readFileSync(0, 'utf8'));
if (typeof event.toolName !== 'string') {
  throw new Error('Expected a Copilot preToolUse event with toolName.');
}
fs.appendFileSync(path.join(__dirname, 'tool-use.log'), `${JSON.stringify(event.toolName)}\n`);
// {} = nessuna decisione sui permessi (non approva il tool).
process.stdout.write('{}');

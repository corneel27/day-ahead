const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');

exports.activate = context => {
  const run = () => require('./tests').run();
  context.subscriptions.push(vscode.commands.registerCommand('dayAhead.verifyRuffAdoption', run));
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!root) return;
  const request = path.join(root, '.local', 'run-ruff-acceptance');
  if (fs.existsSync(request)) {
    fs.unlinkSync(request);
    run().catch(error => vscode.window.showErrorMessage(`Ruff acceptance failed: ${error.message}`));
  }
};

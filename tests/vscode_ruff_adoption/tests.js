// Run inside the actual VS Code extension host, not a mocked language client.
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function until(check, description) {
  for (let attempt = 0; attempt < 120; attempt++) {
    if (await check()) return;
    await delay(250);
  }
  throw new Error(`Timed out: ${description}`);
}

exports.run = async () => {
  const root = vscode.workspace.workspaceFolders[0].uri.fsPath;
  const directory = fs.mkdtempSync(path.join(root, 'ruff-editor-acceptance-cases-'));
  const outputDirectory = path.join(root, '.local', 'ruff-editor-acceptance');
  fs.mkdirSync(directory, {recursive: true});
  fs.mkdirSync(outputDirectory, {recursive: true});
  const launcher = path.join(root, '.venv-tools', process.platform === 'win32' ? 'ruff-project.exe' : 'ruff-project');
  const cases = JSON.parse(fs.readFileSync(path.join(root, 'tests', 'ruff_adoption_cases.json'), 'utf8'));
  const result = {vscode: vscode.version, remoteName: vscode.env.remoteName || null, checks: []};
  const codes = uri => vscode.languages.getDiagnostics(uri)
    .filter(item => item.source === 'Ruff')
    .map(item => typeof item.code === 'object' ? item.code.value : item.code).sort();
  const cli = filename => {
    const check = spawnSync(launcher, ['check', '--output-format', 'json', filename], {cwd: root, encoding: 'utf8'});
    assert.ok([0, 1].includes(check.status), check.stderr);
    return JSON.parse(check.stdout).map(item => item.code).sort();
  };
  try {
    assert.ok(vscode.workspace.isTrusted, 'Trust this test workspace before running editor acceptance; untrusted workspaces can use bundled Ruff');
    const pin = fs.readFileSync(path.join(root, 'requirements-lint.txt'), 'utf8').match(/^ruff==(.+)$/m)[1].trim();
    const version = spawnSync(launcher, ['--version'], {cwd: root, encoding: 'utf8'});
    assert.equal(version.status, 0, version.stderr);
    assert.equal(version.stdout.trim(), `ruff ${pin}`);
    result.ruffVersion = pin;
    result.workspaceTrusted = true;
    const extension = vscode.extensions.getExtension('charliermarsh.ruff');
    assert.ok(extension, 'Install the Ruff extension in this extension host');
    await extension.activate();
    for (const item of cases) {
      const filename = path.join(directory, `${item.code}.py`);
      const expectedFile = path.join(directory, `${item.code}_expected.py`);
      const uri = vscode.Uri.file(filename);
      try {
        fs.writeFileSync(filename, item.invalid);
        const document = await vscode.workspace.openTextDocument(uri);
        const editor = await vscode.window.showTextDocument(document);
        await until(() => codes(uri).includes(item.code), `${item.code} editor diagnostic`);
        assert.deepEqual(codes(uri), cli(filename));
        // Make an explicit editor edit and save; a disk write is not a save test.
        await editor.edit(edit => edit.insert(document.positionAt(document.getText().length), '# save probe\n'));
        fs.writeFileSync(expectedFile, document.getText());
        const fixed = spawnSync(launcher, ['check', '--fix', expectedFile], {cwd: root, encoding: 'utf8'});
        assert.ok([0, 1].includes(fixed.status), fixed.stderr);
        const expectedText = fs.readFileSync(expectedFile, 'utf8').replace(/\r\n/g, '\n');
        await document.save();
        await until(() => document.getText().replace(/\r\n/g, '\n') === expectedText, `${item.code} safe save fixes match CLI`);
        await until(() => JSON.stringify(codes(uri)) === JSON.stringify(cli(filename)), `${item.code} diagnostics after save`);
        await editor.edit(edit => edit.replace(new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length)), item.corrected));
        await document.save();
        await until(() => codes(uri).length === 0, `${item.code} corrected editor diagnostic`);
        assert.deepEqual(cli(filename), []);
        result.checks.push({rule: item.code, diagnostics: 'passed', save: 'passed', corrected: 'passed'});
      } finally {
        await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
        for (const filenameToRemove of [filename, expectedFile]) {
          if (fs.existsSync(filenameToRemove)) fs.unlinkSync(filenameToRemove);
        }
      }
    }
    result.outcome = 'success';
  } catch (error) {
    result.outcome = 'failure';
    result.error = String(error.stack || error);
    throw error;
  } finally {
    fs.writeFileSync(path.join(outputDirectory, 'results.json'), JSON.stringify(result, null, 2));
    fs.rmdirSync(directory);
  }
};

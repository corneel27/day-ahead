import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const verifier = new URL('./verify_node_runtime.mjs', import.meta.url);

test('the development runtime passes the LTS check', () => {
  const result = spawnSync(process.execPath, [fileURLToPath(verifier)], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Node\.js v\d+\.\d+\.\d+: LTS \S+/);
});

test('a runtime without an LTS designation fails the same executable check', () => {
  const result = spawnSync(process.execPath, [
    '--input-type=module', '--eval',
    `delete process.release.lts; await import(${JSON.stringify(verifier.href)});`,
  ], { encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Expected a Node\.js LTS runtime/);
});

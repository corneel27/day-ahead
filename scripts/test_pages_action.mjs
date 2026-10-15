// Exercise the published deployment bundle against local API fixtures, without GitHub credentials.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const actionDir = path.resolve(process.env.PAGES_ACTION_DIR || '.local/deploy-pages');
const build = 'a'.repeat(40);
const artifact = { databaseId: '42', name: 'github-pages', size: '128' };
const runtimeToken = ['e30', Buffer.from(JSON.stringify({
  scp: 'Actions.Results:123:456',
})).toString('base64url'), 'fixture-signature'].join('.');

async function runAction(t, { artifacts = [artifact], deploymentStatus = 'succeed', createStatus = 200 } = {}) {
  const requests = [];
  const unexpected = [];
  let polls = 0;
  const directory = await mkdtemp(path.join(os.tmpdir(), 'pages-action-'));
  const outputFile = path.join(directory, 'output');
  await writeFile(outputFile, '');
  const server = http.createServer(async (request, response) => {
    let raw = '';
    for await (const chunk of request) raw += chunk;
    const body = raw ? JSON.parse(raw) : undefined;
    requests.push({ method: request.method, url: request.url, body });
    response.setHeader('content-type', 'application/json');
    if (request.url === '/oidc') {
      response.end(JSON.stringify({ value: 'synthetic-oidc-token' }));
    } else if (request.url === '/twirp/github.actions.results.api.v1.ArtifactService/ListArtifacts') {
      response.end(JSON.stringify({ artifacts }));
    } else if (request.method === 'POST' && request.url === '/repos/fixture/pages/pages/deployments') {
      response.statusCode = createStatus;
      response.end(JSON.stringify(createStatus === 200
        ? { id: 'deployment-1', page_url: 'https://fixture.invalid/developer/' }
        : { message: 'Pages permission denied' }));
    } else if (request.method === 'GET' && request.url === '/repos/fixture/pages/pages/deployments/deployment-1') {
      polls += 1;
      response.end(JSON.stringify({ status: polls === 1 ? 'building' : deploymentStatus }));
    } else {
      unexpected.push(`${request.method} ${request.url}`);
      response.statusCode = 500;
      response.end(JSON.stringify({ message: 'Unexpected fixture request' }));
    }
  });
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await rm(directory, { recursive: true, force: true });
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const origin = `http://127.0.0.1:${server.address().port}`;
  // Use an allowlist so tokens and endpoint overrides from the CI runner cannot leak into the child.
  const env = Object.fromEntries(['PATH', 'Path', 'SystemRoot', 'TEMP', 'TMP', 'HOME']
    .filter(key => process.env[key]).map(key => [key, process.env[key]]));
  Object.assign(env, {
    GITHUB_RUN_ID: '123', GITHUB_REPOSITORY: 'fixture/pages', GITHUB_SHA: build,
    GITHUB_ACTOR: 'fixture', GITHUB_ACTION: 'deployment', GITHUB_OUTPUT: outputFile,
    GITHUB_API_URL: origin, GITHUB_SERVER_URL: 'https://github.com',
    ACTIONS_RESULTS_URL: origin, ACTIONS_RUNTIME_TOKEN: runtimeToken,
    ACTIONS_ID_TOKEN_REQUEST_URL: `${origin}/oidc`, ACTIONS_ID_TOKEN_REQUEST_TOKEN: 'fixture',
    INPUT_TOKEN: 'fixture', INPUT_ARTIFACT_NAME: 'github-pages', INPUT_PREVIEW: 'false',
    INPUT_TIMEOUT: '5000', INPUT_ERROR_COUNT: '2', INPUT_REPORTING_INTERVAL: '1',
  });
  const child = spawn(process.execPath, [path.join(actionDir, 'dist/index.js')], {
    env, cwd: directory, timeout: 15000,
  });
  let log = '';
  child.stdout.on('data', data => { log += data; });
  child.stderr.on('data', data => { log += data; });
  const [code, signal] = await once(child, 'close');
  assert.equal(signal, null, log);
  assert.deepEqual(unexpected, [], log);
  return { code, log, requests, polls, output: await readFile(outputFile, 'utf8') };
}

test('the published action runs on its declared Node runtime', async () => {
  const metadata = await readFile(path.join(actionDir, 'action.yml'), 'utf8');
  const runtime = metadata.match(/using:\s*['"]?node(\d+)/)?.[1];
  assert.equal(process.versions.node.split('.')[0], runtime);
});

test('the published bundle selects the Pages artifact, deploys, polls and returns its URL', async t => {
  const result = await runAction(t, { artifacts: [{ ...artifact, databaseId: '99', name: 'unrelated' }, artifact] });
  assert.equal(result.code, 0, result.log);
  assert.equal(result.polls, 2);
  const request = result.requests.find(item => item.method === 'POST' && item.url.endsWith('/pages/deployments'));
  assert.deepEqual(request.body, { artifact_id: 42, pages_build_version: build, oidc_token: 'synthetic-oidc-token' });
  assert.match(result.output, /https:\/\/fixture\.invalid\/developer\//);
  assert.match(result.output, /succeed/);
});

test('a missing Pages artifact fails before attempting deployment', async t => {
  const result = await runAction(t, { artifacts: [] });
  assert.equal(result.code, 1, result.log);
  assert.match(result.log, /No artifacts named "github-pages"/);
  assert.equal(result.requests.filter(item => item.url.includes('/pages/deployments')).length, 0);
});

test('a rejected deployment surfaces the required Pages permission', async t => {
  const result = await runAction(t, { createStatus: 403 });
  assert.equal(result.code, 1, result.log);
  assert.match(result.log, /pages: write/);
  assert.equal(result.polls, 0);
});

test('a failed deployment cannot be reported as success', async t => {
  const result = await runAction(t, { deploymentStatus: 'deployment_failed' });
  assert.equal(result.code, 1, result.log);
  assert.equal(result.polls, 2);
  assert.match(result.log, /Deployment failed/);
  assert.doesNotMatch(result.output, /succeed/);
});

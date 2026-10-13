import assert from 'node:assert/strict';
import test from 'node:test';
import { developerGuideUrl, launchUrl, repositoryUrl } from './start.mjs';

test('only cloneable repository URLs are passed to the browser launch URI', () => {
  for (const value of [
    'https://github.com/patrickvorgers/day-ahead',
    'https://github.com/another-user/my-fork',
  ]) {
    const launch = new URL(launchUrl(value));
    assert.equal(launch.protocol, 'vscode:');
    assert.equal(launch.host, 'ms-vscode-remote.remote-containers');
    assert.equal(launch.pathname, '/cloneInVolume');
    assert.equal(launch.searchParams.get('url'), value);
  }
});

test('branch URLs never reach the URI handler repository-access check', () => {
  for (const repo of [
    'https://github.com/patrickvorgers/day-ahead/tree/chore/development-environment',
    'https://github.com/another-user/my-fork/tree/feature%2Fruff',
  ]) assert.throws(() => launchUrl(repo), /Clone Repository in Container Volume/);
});

test('copy-pasted clone URL is normalized without changing the owner', () => {
  assert.equal(repositoryUrl(' https://github.com/my-user/day-ahead.git/ '), 'https://github.com/my-user/day-ahead');
  assert.equal(developerGuideUrl('https://github.com/my-user/day-ahead'), 'https://github.com/my-user/day-ahead/blob/HEAD/DEVELOP.md');
  assert.equal(developerGuideUrl('https://github.com/my-user/day-ahead/tree/chore/development-environment'), 'https://github.com/my-user/day-ahead/blob/chore/development-environment/DEVELOP.md');
});

test('non-repository URLs and credential-bearing links never launch', () => {
  for (const value of [
    '', 'github.com/owner/repo', 'javascript:alert(1)', 'http://github.com/owner/repo',
    'https://github.com.evil.test/owner/repo', 'https://user:secret@github.com/owner/repo',
    'https://github.com:8443/owner/repo', 'https://github.com/owner',
    'https://github.com/owner/repo/issues/1', 'https://github.com/owner/repo/tree/',
    'https://github.com/owner/repo?token=secret', 'https://github.com/owner/repo#fragment',
  ]) assert.throws(() => launchUrl(value));
});

test('branch submission shows instructions; repository submission launches VS Code', async () => {
  const repo = 'https://github.com/patrickvorgers/day-ahead/tree/chore/development-environment';
  const elements = new Map();
  for (const id of ['#start-form', '#repository', '#error', '#launch', '#guide', '#clone-url', '#next', '#open', '#next-title', '#instructions']) {
    elements.set(id, { hidden: true, focus() {}, addEventListener(event, handler) { this.submit = handler; } });
  }
  const initial = `https://patrickvorgers.github.io/day-ahead/developer/?repository=${encodeURIComponent(repo)}`;
  globalThis.document = { querySelector: id => elements.get(id) };
  globalThis.location = { href: initial };
  try {
    await import('./start.mjs?form-test');
    assert.equal(elements.get('#repository').value, repo);
    assert.equal(elements.get('#open').textContent, 'Show branch instructions');
    assert.equal(location.href, initial);
    elements.get('#repository').value = 'https://other-site.test/owner/repo';
    elements.get('#start-form').submit({ preventDefault() {} });
    assert.equal(location.href, initial);
    assert.equal(elements.get('#error').hidden, false);
    assert.equal(elements.get('#next').hidden, true);
    elements.get('#repository').value = repo;
    elements.get('#start-form').submit({ preventDefault() {} });
    assert.equal(location.href, initial);
    assert.equal(elements.get('#launch').hidden, true);
    assert.equal(elements.get('#clone-url').textContent, repo);
    assert.match(elements.get('#instructions').textContent, /VS Code clone command/);
    assert.equal(elements.get('#error').hidden, true);
    assert.equal(elements.get('#next').hidden, false);
    const root = 'https://github.com/patrickvorgers/day-ahead';
    elements.get('#repository').value = root;
    elements.get('#repository').submit();
    assert.equal(elements.get('#open').textContent, 'Open in VS Code');
    elements.get('#start-form').submit({ preventDefault() {} });
    assert.equal(location.href, launchUrl(root));
    assert.equal(elements.get('#launch').href, launchUrl(root));
    assert.equal(elements.get('#launch').hidden, false);
  } finally {
    delete globalThis.document;
    delete globalThis.location;
  }
});

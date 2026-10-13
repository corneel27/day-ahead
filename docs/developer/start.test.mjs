import assert from 'node:assert/strict';
import test from 'node:test';
import { developerGuideUrl, launchUrl, repositoryUrl } from './start.mjs';

test('fork URLs and branch URLs survive a VS Code URI round trip', () => {
  for (const value of [
    'https://github.com/patrickvorgers/day-ahead',
    'https://github.com/patrickvorgers/day-ahead/tree/chore/development-environment',
    'https://github.com/another-user/my-fork/tree/feature%2Fruff',
  ]) {
    const launch = new URL(launchUrl(value));
    assert.equal(launch.protocol, 'vscode:');
    assert.equal(launch.host, 'ms-vscode-remote.remote-containers');
    assert.equal(launch.pathname, '/cloneInVolume');
    assert.equal(launch.searchParams.get('url'), value);
  }
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

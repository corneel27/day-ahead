import assert from 'node:assert/strict';

// Inspect the running binary, rather than inferring LTS status from a major number.
assert.ok(
  typeof process.release.lts === 'string' && process.release.lts.length > 0,
  `Expected a Node.js LTS runtime, got ${process.version} without an LTS designation`,
);
console.log(`Node.js ${process.version}: LTS ${process.release.lts}`);

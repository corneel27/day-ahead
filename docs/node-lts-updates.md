# Node.js updates in the development container

The development Dockerfile uses the official `node:lts-bookworm-slim` tag,
pinned to a multi-platform image digest. The tag follows the Active LTS
release selected by the Node.js Docker maintainers. It does not select
the Current release or require a list of allowed major versions.

The digest keeps the selected image fixed: rebuilding a checkout cannot
silently move to a different Node release when the tag changes. Dependabot
checks this tag weekly and proposes digest updates, including a new major
when it becomes Active LTS. The Node cooldown exclusion allows updates even
when this floating tag has just been republished. Keep both the LTS tag and
the digest when reviewing those proposals.

Every proposed update must pass the clean development-container installation,
frontend build, application regression tests, synthetic solver scenarios and
browser tests before merging. `scripts/verify_node_runtime.mjs` additionally
checks the running binary's LTS designation; its regression test verifies that
a runtime without that designation is rejected. These checks use isolated
fixtures and do not control Home Assistant devices.

LTS designation alone does not prove that a pinned release is still supported:
an old LTS binary retains its designation after end-of-life. Review and merge
the update proposals promptly, and check support dates against the official
[Node release schedule](https://github.com/nodejs/Release#release-schedule).
The Docker tag policy is documented in the
[official Node image documentation](https://github.com/nodejs/docker-node#image-variants).

This policy changes the development container; the Python application image
is maintained separately.

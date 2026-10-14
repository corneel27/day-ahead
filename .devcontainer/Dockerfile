FROM node:22-bookworm-slim AS node
FROM python:3.13-bookworm

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && apt-get update \
    && apt-get install -y --no-install-recommends git build-essential pkg-config libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=UTC
ENV MPLBACKEND=Agg

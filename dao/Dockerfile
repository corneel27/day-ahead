ARG BUILD_FROM

# ==============================================================================
# Stage 1: Builder - Build frontend and generate schemas
# ==============================================================================
FROM ${BUILD_FROM} as builder

ARG BUILD_ARCH

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install build dependencies (including MariaDB dev libs for Python mariadb package)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update -y && \
  apt-get install -y pkgconf nano file mariadb-client inotify-tools procps \
    gunicorn libmariadb3 libmariadb-dev postgresql-client sqlite3 libjpeg-dev libffi-dev \
    wget libnauty-dev coinor-libcgl-dev gcc g++ git \
    python3 python3-pip python3-venv

# Install Node.js 24 LTS (current LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
  apt-get install -y nodejs && \
  rm -rf /var/lib/apt/lists/*

# Install pnpm globally
RUN npm install -g pnpm@9

# Set up Python build environment
WORKDIR /build
ENV VIRTUAL_ENV=/build/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install Python dependencies for schema generation
RUN pip3 install uv
COPY requirements.txt /build/
RUN if [ "x${BUILD_ARCH}" = "xaarch64" ]; then ln -s `which mariadb_config` /usr/local/bin/mariadb_config; fi
RUN uv pip install -r requirements.txt

# Copy Python source with expected directory structure (script expects dao/prog)
RUN mkdir -p /build/dao
COPY prog/ /build/dao/prog/

# Copy frontend with schema generation script
COPY frontend/ /build/dao/frontend/

# Generate schemas
RUN mkdir -p /build/schemas && \
    PYTHONPATH=/build/dao/prog python3 /build/dao/frontend/generate_uischema.py \
        --quiet --output-dir /build/schemas

# Build frontend
WORKDIR /build/dao/frontend

# Install frontend dependencies
RUN pnpm install --frozen-lockfile

# Build frontend (creates dist/)
RUN pnpm build

# Verify build outputs exist
RUN test -f /build/dao/frontend/dist/index.html && \
    test -f /build/schemas/schema.json && \
    test -f /build/schemas/uischema.json && \
    echo "✅ Build verification passed"


# ==============================================================================
# Stage 2: Runtime - Final lean image
# ==============================================================================
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ENV ENV_BUILD_ARCH=$BUILD_ARCH

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update -y && \
  apt-get upgrade -y && \
  apt-get install -y pkgconf nano file mariadb-client inotify-tools procps \
    gunicorn libmariadb3 libmariadb-dev postgresql-client sqlite3 libjpeg-dev libffi-dev \
    wget libnauty-dev coinor-libcgl-dev gcc g++ git \
    python3 python3-pip python3-venv

# Copy software for add-on
RUN mkdir /root/dao
COPY __init__.py /root/dao
COPY lib /root/dao/lib/
COPY prog /root/dao/prog/
COPY webserver /root/dao/webserver/
COPY data /tmp/daodata/

# Copy built frontend from builder stage
COPY --from=builder /build/dao/frontend/dist/ /root/dao/webserver/app/static/config-ui/

# Copy generated schemas from builder stage
COPY --from=builder /build/schemas/ /root/dao/webserver/app/static/schemas/

#version
ARG BUILD_VERSION
ENV DAO_VERSION=$BUILD_VERSION
RUN printf  '__version__ ="%s"\n' "$DAO_VERSION" > /root/dao/prog/version.py


WORKDIR /root/dao/prog
RUN echo 'platform: "$ENV_BUILD_ARCH"' \
  && export BUILD_ARCH="$ENV_BUILD_ARCH" \
  && echo 'export BUILD_ARCH="$ENV_BUILD_ARCH"' >> ~/.bashrc \
  && export PYTHONPATH="/root:/root/dao:/root/dao/prog" \
  && echo 'export PYTHONPATH="/root:/root/dao:/root/dao/prog"' >> ~/.bashrc

ENV VIRTUAL_ENV=/root/dao/venv/day_ahead
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip3 install uv
RUN if [ "x${BUILD_ARCH}" = "xaarch64" ]; then ln -s `which mariadb_config` /usr/local/bin/mariadb_config; fi
RUN --mount=type=bind,target=/tmp uv pip install -r /tmp/requirements.txt

COPY run /root/dao/prog/

EXPOSE 5000
WORKDIR /root/dao/prog
RUN chmod a+x run.sh
ENTRYPOINT  ["./run.sh"]

# Labels
LABEL \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION}

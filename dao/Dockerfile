ARG BUILD_ARCH
ARG BUILD_VERSION

FROM ghcr.io/hassio-addons/debian-base/${BUILD_ARCH}:9.3.0

ENV ENV_BUILD_ARCH=$BUILD_ARCH
ENV DAO_VERSION=${BUILD_VERSION}


SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y pkgconf file inotify-tools procps gunicorn sqlite3 \
      libmariadb-dev postgresql-client libjpeg-dev libffi-dev \
      libnauty-dev coinor-libcgl-dev gcc g++ libmariadb3 mariadb-client \
      python3 python3-venv python3-pip npm && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /root/dao
WORKDIR /root/dao
ENV VIRTUAL_ENV=/root/dao/venv/day_ahead
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONPATH=/root:/root/dao:/root/dao/prog
RUN python3 -m venv $VIRTUAL_ENV

COPY requirements.txt /tmp/requirements.txt

RUN if [ "x${BUILD_ARCH}" = "xaarch64" ]; then ln -s `which mariadb_config` /usr/local/bin/mariadb_config; fi
RUN source $VIRTUAL_ENV/bin/activate \
    && pip3 install uv \
    && uv pip install  -r /tmp/requirements.txt \
    && pip3 uninstall -y uv

COPY webserver/package.json webserver/package-lock.json webserver/vite.config.js /root/dao/webserver/
COPY webserver/assets /root/dao/webserver/assets

WORKDIR /root/dao/webserver
RUN  npm ci \
     && npm run build

# Copy software for add-on
COPY --from=builder /root/dao/webserver/app/static/build /root/dao/webserver/app/static/build
COPY --from=builder /root/dao/venv /root/dao/venv
COPY __init__.py /root/dao
COPY lib /root/dao/lib/
COPY prog /root/dao/prog/
COPY webserver /root/dao/webserver/
COPY data /tmp/daodata/

#version
RUN printf  '__version__ ="%s"\n' "$DAO_VERSION" > /root/dao/prog/version.py

WORKDIR /root/dao/prog
RUN echo 'platform: "$ENV_BUILD_ARCH"' \
  && export BUILD_ARCH="$ENV_BUILD_ARCH" \
  && echo 'export BUILD_ARCH="$ENV_BUILD_ARCH"' >> ~/.bashrc \
  && export PYTHONPATH="/root:/root/dao:/root/dao/prog" \
  && echo 'export PYTHONPATH="/root:/root/dao:/root/dao/prog"' >> ~/.bashrc

COPY run /root/dao/prog/

EXPOSE 5000
WORKDIR /root/dao/prog
RUN chmod a+x run.sh
ENTRYPOINT  ["./run.sh"]

# Labels
LABEL \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.source="https://github.com/corneel27/day-ahead"

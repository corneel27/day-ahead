ARG BUILD_FROM
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
COPY prog /root/dao/prog/
COPY webserver /root/dao/webserver/
COPY data /tmp/daodata/

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

RUN --mount=type=bind,target=/tmp tar -xzf /tmp/miplib_${BUILD_ARCH}.tar.gz -C /root/dao/prog

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
ENTRYPOINT  ["/bin/bash", "./run.sh"]

# Labels
LABEL \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION}

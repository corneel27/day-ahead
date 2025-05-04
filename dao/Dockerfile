ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ENV ENV_BUILD_ARCH=$BUILD_ARCH

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update -y
RUN apt-get upgrade -y

#handige tools
RUN apt-get install -y pkgconf nano file mariadb-client inotify-tools procps gunicorn libmariadb3 libmariadb-dev
RUN apt-get install -y postgresql-client sqlite3 gcc

# Copy software for add-on
RUN mkdir /root/dao
COPY __init__.py /root/dao
COPY prog /root/dao/prog/
COPY webserver /root/dao/webserver/
# COPY dao/__init__.py /root/dao
COPY data /tmp/daodata/

#version
ARG BUILD_VERSION
ENV DAO_VERSION=$BUILD_VERSION
RUN printf  '__version__ ="%s"\n' "$DAO_VERSION" > /root/dao/prog/version.py

#benodigde libraries voor mip
RUN apt-get install -y wget libnauty2-dev coinor-libcgl-dev libcholmod3

COPY miplib.tar.gz /tmp/
WORKDIR /root/dao/prog
RUN echo 'platform: "$ENV_BUILD_ARCH"' \
  && export BUILD_ARCH="$ENV_BUILD_ARCH" \
  && echo 'export BUILD_ARCH="$ENV_BUILD_ARCH"' >> ~/.bashrc \
  && export PYTHONPATH="/root:/root/dao:/root/dao/prog" \
  && echo 'export PYTHONPATH="/root:/root/dao:/root/dao/prog"' >> ~/.bashrc

RUN if [ "${BUILD_ARCH}" = "aarch64" ]; then \
      tar -xvf /tmp/miplib.tar.gz -C /root/dao/prog && \
      export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so" && \
      export LD_LIBRARY_PATH="/root/dao/prog/miplib/lib/"  && \
      echo 'export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"' >> ~/.bashrc  && \
      echo 'export LD_LIBRARY_PATH="/root/dao/prog/miplib/lib/"' >> ~/.bashrc \
   ; fi

#installeer python en pip
RUN apt-get install python3 -y\
    python3-pip -y\
    python3-venv -y

ENV VIRTUAL_ENV=/root/dao/venv/day_ahead
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /tmp/
RUN pip3 install uv
RUN uv pip install -r /tmp/requirements.txt
COPY run /root/dao/prog/

EXPOSE 5000
WORKDIR /root/dao/prog
RUN chmod a+x run.sh
ENTRYPOINT  ["/bin/bash", "./run.sh"]


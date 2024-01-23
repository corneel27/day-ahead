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

# Copy software for add-on
RUN mkdir /root/dao
COPY prog /root/dao/prog/
COPY webserver /root/dao/webserver/
COPY data /tmp/daodata/

#version
ARG BUILD_VERSION
ENV DAO_VERSION=$BUILD_VERSION
# RUN printf  '__version__ ="%s"\n' "$DAO_VERSION" > /root/dao/prog/_version.py

#benodigde libraries voor mip
RUN apt-get install -y wget libnauty2-dev coinor-libcgl-dev libcholmod3

COPY miplib.tar.gz /tmp/
WORKDIR /root/dao/prog
RUN echo 'platform: "$ENV_BUILD_ARCH"' \
  && export BUILD_ARCH="$ENV_BUILD_ARCH" \
  && echo 'export BUILD_ARCH="$ENV_BUILD_ARCH"' >> ~/.bashrc

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
RUN pip3 install -r /tmp/requirements.txt

EXPOSE 5000
WORKDIR /root/dao/prog
RUN chmod a+x run.sh
RUN chmod a+x run_loop.sh
CMD ["/bin/bash", "./run.sh"]
# CMD ["./run_loop.sh"]
#
#CMD ["top"]


ARG BUILD_FROM
FROM ${BUILD_FROM}

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

#benodigde libraries voor mip
RUN apt-get install -y wget libnauty2-dev coinor-libcgl-dev libcholmod3

# COPY miplib/ /root/prog/miplib/
COPY miplib.tar.gz /tmp/
WORKDIR /root/dao/prog
RUN tar -xvf /tmp/miplib.tar.gz
RUN export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"
RUN export LD_LIBRARY_PATH="/root/dao/prog/miplib/lib/"
RUN echo 'export PMIP_CBC_LIBRARY="/root/dao/prog/miplib/lib/libCbc.so"' >> ~/.bashrc
RUN echo 'export LD_LIBRARY_PATH="/root/dao/prog/miplib/lib/"' >> ~/.bashrc

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


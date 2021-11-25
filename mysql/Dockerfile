FROM quay.io/iovisor/bcc:v0.23.0-focal-release

# Originally this image was using a multi-stage builder. However, in that
# architecture, whenever docker system prune runs, it prunes the builder image
# layers, which means if you run docker build after, it will try to build MySQL
# again, which is really really slow.

RUN set -xe; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y \
      bison \
      build-essential \
      cmake \
      curl \
      git \
      libaio-dev \
      libcurl4-openssl-dev \
      libldap2-dev \
      libncurses-dev \
      libreadline-dev \
      libssl-dev \
      pkg-config \
      systemtap-sdt-dev \
      zlib1g-dev \
    ;

COPY build-mysql.sh /opt/build-mysql.sh

ARG PERCONA_VERSION=5.7.35-38
ENV PERCONA_VERSION=${PERCONA_VERSION}

RUN /opt/build-mysql.sh

RUN set -xe; \
    adduser --gecos "" --system --group mysql; \
    mkdir -p /data/mysql; \
    mkdir -p /opt/bin;

RUN apt-get install -y linux-headers-$(uname -r)

COPY my.cnf /etc/my.cnf
COPY bin /opt/bin

CMD ["/opt/bin/start-mysql.sh"]


FROM ubuntu:focal

RUN set -xe; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y sysbench curl readline-common libreadline8 debsums; \
    mkdir /tmp/mysql; \
    cd /tmp/mysql; \
    curl -SLO https://downloads.percona.com/downloads/Percona-Server-LATEST/Percona-Server-8.0.26-16/binary/debian/focal/x86_64/percona-server-common_8.0.26-16-1.focal_amd64.deb; \
    curl -SLO https://downloads.percona.com/downloads/Percona-Server-LATEST/Percona-Server-8.0.26-16/binary/debian/focal/x86_64/percona-server-client_8.0.26-16-1.focal_amd64.deb; \
    dpkg -i percona-server-common_8.0.26-16-1.focal_amd64.deb; \
    dpkg -i percona-server-client_8.0.26-16-1.focal_amd64.deb;

COPY bin /app/bin

CMD ["sleep", "infinity"]

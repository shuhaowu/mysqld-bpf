#!/bin/bash

set -xe

export PATH=/usr/local/mysql/bin:$PATH

/opt/bin/init-mysql.sh

chown -R mysql:mysql /data
chown -R mysql:mysql /var/run/mysqld

exec mysqld --defaults-file=/etc/my.cnf --server-id=1 --user=mysql


#!/bin/bash

MYSQLD="mysqld --defaults-file=/etc/my.cnf"
MYSQL="mysql -S /var/run/mysqld/mysqld.sock"

set -xe

mkdir -p /var/run/mysqld
chown mysql:mysql /var/run/mysqld

if [ ! -d /data/mysql ]; then
  echo "error: /data/mysql not mounted!" >&2
  exit 1
fi

server_id=1

if [ ! "$(ls -A /data/mysql/data)" ]; then
  # Initialize the data volume
  mkdir -p /data/mysql/data
  mkdir -p /data/mysql/logs
  mkdir -p /data/mysql/tmp

  chown -R mysql:mysql /data
  $MYSQLD --initialize-insecure --user=mysql --server-id=$server_id
fi

# Initialize
$MYSQLD --server-id=$server_id --skip-networking --user=mysql &
pid="$!"

set +x

for i in {120..0}; do
  if $MYSQL -e "SELECT 1" >/dev/null; then
    break
  fi

  echo "Waiting for MySQL startup..."
  sleep 1
done

if [ "$i" == 0 ]; then
  echo "error: MySQL startup failed" >&2
  exit 1
fi

cat | $MYSQL <<EOF
SET SESSION sql_log_bin = OFF;
CREATE USER IF NOT EXISTS 'admin'@'%';
SET PASSWORD FOR 'admin'@'%' = 'hunter2';
GRANT ALL PRIVILEGES ON *.* TO 'admin'@'%' WITH GRANT OPTION;
EOF

set -x

if ! kill -s TERM "$pid" || ! wait "$pid"; then
  echo >&2 'MySQL init process failed.'
  exit 1
fi


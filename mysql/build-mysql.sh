#!/bin/bash

set -e

mkdir /tmp/build
pushd /tmp/build

if [[ "$PERCONA_VERSION" =~ ^8\.0.* ]]; then
  download_url="https://downloads.percona.com/downloads/Percona-Server-LATEST/Percona-Server-${PERCONA_VERSION}/source/tarball/percona-server-${PERCONA_VERSION}.tar.gz"

  cmake_flags=""
  cmake_flags+="-DBUILD_CONFIG=mysql_release "
  cmake_flags+="-DCMAKE_BUILD_TYPE=RelWithDebInfo "
  cmake_flags+="-DDOWNLOAD_BOOST=1 "
  cmake_flags+="-DFEATURE_SET=community "
  cmake_flags+="-DFORCE_INSOURCE_BUILD=1 "
  cmake_flags+="-DWITH_AUTHENTICATION_LDAP=OFF "
  cmake_flags+="-DWITH_BOOST=/tmp/build/boost "
  cmake_flags+="-DWITH_EMBEDDED_SERVER=OFF "
  cmake_flags+="-DWITH_ZLIB=bundled"
elif [[ "$PERCONA_VERSION" =~ ^5\.7.* ]]; then
  download_url="https://downloads.percona.com/downloads/Percona-Server-5.7/Percona-Server-${PERCONA_VERSION}/source/tarball/percona-server-${PERCONA_VERSION}.tar.gz"

  cmake_flags=""
  cmake_flags+="-DBUILD_CONFIG=mysql_release "
  cmake_flags+="-DCMAKE_BUILD_TYPE=RelWithDebInfo "
  cmake_flags+="-DDOWNLOAD_BOOST=1 "
  cmake_flags+="-DENABLE_DTRACE=1 "
  cmake_flags+="-DFEATURE_SET=community "
  cmake_flags+="-DWITH_BOOST=/tmp/build/boost "
  cmake_flags+="-DWITH_EMBEDDED_SERVER=OFF "
  cmake_flags+="-DWITH_ZLIB=bundled"
else
  echo "error: only 5.7 and 8.0 is supported, not $PERCONA_VERSION" >&2
  exit 1
fi

set -x

curl -SLO $download_url
tar xf percona-server-${PERCONA_VERSION}.tar.gz
cd percona-server-${PERCONA_VERSION}
cmake . $cmake_flags
make -j$(nproc)
make install

popd
# Do not remove for now, so I can use pahole
# rm -rf /tmp/build

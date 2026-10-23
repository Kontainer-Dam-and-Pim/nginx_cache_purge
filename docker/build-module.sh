#!/bin/sh
set -eu

version=$(nginx -v 2>&1 | sed 's|^nginx version: nginx/||')
number=$(echo "$version" | awk -F. '{ printf "%d%03d%03d", $1, $2, $3 }')

if [ "$number" -lt 1021005 ]; then
    pcre_apk=pcre-dev
    pcre_deb=libpcre3-dev
else
    pcre_apk=pcre2-dev
    pcre_deb=libpcre2-dev
fi

# shellcheck source=/dev/null
. /etc/os-release

case $ID in
    alpine)
        apk add --no-cache build-base linux-headers openssl-dev zlib-dev "$pcre_apk"
        ;;
    debian)
        case $VERSION_CODENAME in
            stretch|buster)
                sed -i -e 's|deb.debian.org|archive.debian.org|g' \
                       -e '/security.debian.org/d' -e '/-updates/d' \
                       /etc/apt/sources.list
                echo 'Acquire::Check-Valid-Until "false";' \
                    > /etc/apt/apt.conf.d/99archive
                ;;
        esac
        apt-get update
        apt-get install -y --no-install-recommends \
            build-essential libssl-dev zlib1g-dev "$pcre_deb"
        ;;
    *)
        echo "build-module.sh: no build recipe for $ID" >&2
        exit 1
        ;;
esac

curl -fsS --max-time 120 "https://nginx.org/download/nginx-$version.tar.gz" \
    | tar xz -C /tmp
cd "/tmp/nginx-$version"

args=$(nginx -V 2>&1 | sed -n 's/^configure arguments: //p')
eval "./configure $args --add-dynamic-module=/module"
make modules

mkdir -p /out
cp objs/ngx_http_cache_purge_module.so /out/

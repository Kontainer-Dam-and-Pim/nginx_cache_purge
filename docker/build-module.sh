#!/bin/sh
set -eu

version=$(nginx -v 2>&1 | sed 's|^nginx version: nginx/||')
number=$(echo "$version" | awk -F. '{ printf "%d%03d%03d", $1, $2, $3 }')

if [ "$number" -lt 1021005 ]; then
    pcre_apk=pcre-dev
    pcre_deb=libpcre3-dev
    pcre_rpm=pcre-devel
else
    pcre_apk=pcre2-dev
    pcre_deb=libpcre2-dev
    pcre_rpm=pcre2-devel
fi

# shellcheck source=/dev/null
. /etc/os-release

case $ID in
    alpine)
        apk add --no-cache build-base linux-headers openssl-dev zlib-dev "$pcre_apk"
        ;;
    debian)
        if curl -fsI --max-time 30 \
            "http://archive.debian.org/debian/dists/$VERSION_CODENAME/Release" \
            >/dev/null
        then
            for f in /etc/apt/sources.list /etc/apt/sources.list.d/*; do
                [ -f "$f" ] || continue
                sed -i -e 's|deb.debian.org|archive.debian.org|g' \
                       -e 's|security.debian.org|archive.debian.org|g' \
                       -e '/-updates/d' "$f"
            done
            echo 'Acquire::Check-Valid-Until "false";' \
                > /etc/apt/apt.conf.d/99archive
        fi
        apt-get update
        apt-get install -y --no-install-recommends \
            build-essential libssl-dev zlib1g-dev "$pcre_deb"
        ;;
    rocky)
        dnf -y install gcc make tar gzip redhat-rpm-config \
            openssl-devel zlib-devel "$pcre_rpm"
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
modules=$(echo "$args" | sed -n 's/.*--modules-path=\([^ ]*\).*/\1/p')
if [ -z "$modules" ]; then
    echo "build-module.sh: nginx -V names no --modules-path" >&2
    exit 1
fi
eval "./configure $args --add-dynamic-module=/module"
make modules

mkdir -p "/out$modules"
cp objs/ngx_http_cache_purge_module.so "/out$modules/"

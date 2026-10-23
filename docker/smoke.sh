#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: smoke.sh <image>" >&2
    exit 2
fi

here=$(cd "$(dirname "$0")" && pwd)
name=ngx-cache-purge-smoke-$$
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT

docker run -d --name "$name" -p 127.0.0.1::8080 \
    -v "$here/smoke.conf:/etc/nginx/conf.d/default.conf:ro" "$1" >/dev/null
port=$(docker port "$name" 8080 | head -1 | sed 's/.*://')

for _ in $(seq 50); do
    curl -fsS -o /dev/null "http://127.0.0.1:$port/ready" 2>/dev/null && break
    sleep 0.2
done

request() {
    curl -sS -o /dev/null -X "$1" -w '%{http_code} %header{x-cache}' \
        "http://127.0.0.1:$port/item"
}

expect() {
    local got
    got=$(request "$1")
    if [ "$got" != "$2" ]; then
        echo "smoke.sh: $1 /item answered \"$got\", expected \"$2\"" >&2
        docker logs "$name" >&2
        exit 1
    fi
}

expect GET "200 MISS"
expect GET "200 HIT"
expect PURGE "200 "
expect GET "200 MISS"
echo "smoke: $1 caches, purges and refills"

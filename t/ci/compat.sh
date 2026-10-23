#!/usr/bin/env bash
set -euo pipefail

src=${NGINX_SRC:-/nginx-src}
module=${MODULE_DIR:-/module}
here=$(cd "$(dirname "$0")" && pwd)

echo "== struct layouts: full build ($("$src"/objs/nginx -v 2>&1))"
"$here/struct_layout.py" "$module/ngx_cache_purge_module.c" "$src/objs"

minimal=$(mktemp -d)
trap 'rm -rf "$minimal"' EXIT
cp -a "$src/." "$minimal"
cd "$minimal"
rm -rf objs Makefile

echo "== minimal build with clang: no SSL, no PCRE"
./configure --with-cc=clang --with-cc-opt="-g" \
    --without-http_rewrite_module --without-pcre \
    --with-threads --add-module="$module"
make -j"$(nproc)" >/dev/null

echo "== struct layouts: minimal build"
"$here/struct_layout.py" "$module/ngx_cache_purge_module.c" objs

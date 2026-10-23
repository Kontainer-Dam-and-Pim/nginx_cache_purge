#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: build-nginx.sh <nginx-src> <sanitize: '' or asan,ubsan> [configure args...]" >&2
    exit 2
fi

src=$1
sanitize=$2
shift 2

cc_opt="-g -O2 -fno-omit-frame-pointer"
ld_opt=""
if [ -n "$sanitize" ]; then
    flags=""
    IFS=, read -ra names <<<"$sanitize"
    for name in "${names[@]}"; do
        case $name in
            asan)  flags+=",address" ;;
            ubsan) flags+=",undefined" ;;
            *) echo "build-nginx.sh: unknown sanitizer '$name' in '$sanitize'" >&2; exit 2 ;;
        esac
    done
    flags=${flags#,}
    cc_opt="-g -O1 -fno-omit-frame-pointer -fsanitize=$flags"
    ld_opt="-fsanitize=$flags"
fi

cd "$src"
./configure --with-cc-opt="$cc_opt" --with-ld-opt="$ld_opt" "$@"
make -j"$(nproc)"
make install

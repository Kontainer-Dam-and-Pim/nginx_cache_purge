#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

reports=$(mktemp -d)
trap 'rm -rf "$reports"' EXIT
chmod 1777 "$reports"

export UBSAN_OPTIONS="print_stacktrace=1,suppressions=$PWD/t/ci/ubsan.supp"
export LSAN_OPTIONS="suppressions=$PWD/t/ci/lsan.supp,print_suppressions=0"
export ASAN_OPTIONS="detect_leaks=1,log_path=$reports/asan"

if [ "${VALGRIND:-0}" = 1 ]; then
    export TEST_NGINX_USE_VALGRIND="--tool=memcheck --num-callers=50 --leak-check=no --track-origins=yes --log-file=$reports/valgrind.%p"
fi

if [ $# -eq 0 ]; then
    set -- t/*.t
fi

rc=0
prove -v "$@" || rc=$?

while IFS= read -r -d '' f; do
    echo "::error title=memory error report::${f##*/}"
    cat "$f"
    rc=1
done < <(find "$reports" -type f -size +0 -print0)

exit $rc

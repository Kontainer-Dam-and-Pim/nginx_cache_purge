#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: analyze.sh <nginx source dir> <SARIF output dir>" >&2
    exit 2
fi

repo=$(cd "$(dirname "$0")/../.." && pwd)
module=$repo/ngx_cache_purge_module.c
mkdir -p "$2"
out=$(cd "$2" && pwd)
cd "$1"

./configure --with-threads --with-file-aio --with-http_ssl_module \
    --with-http_v2_module --add-module="$repo" >/dev/null
# shellcheck disable=SC2016
read -ra incs <<<"$(make -s -f objs/Makefile -f - print-incs <<<'print-incs: ; @echo $(ALL_INCS)')"

gcc_warnings=(-Wall -Wextra -Wno-unused-parameter -Wshadow -Wformat=2
    -Wduplicated-cond -Wduplicated-branches -Wlogical-op -Wmissing-prototypes
    -Wstrict-prototypes -Wvla -Wimplicit-fallthrough -Wstrict-overflow=2 -Walloca)
clang_warnings=(-Wall -Wno-unused-parameter -Wshadow -Wformat=2
    -Wmissing-prototypes -Wstrict-prototypes -Wcomma -Wunreachable-code
    -Wconditional-uninitialized -Wshorten-64-to-32 -Wloop-analysis)

echo "== gcc warnings"
gcc -O2 -Werror "${gcc_warnings[@]}" "${incs[@]}" -c "$module" -o /dev/null

echo "== clang warnings"
clang -O2 -Werror "${clang_warnings[@]}" "${incs[@]}" -c "$module" -o /dev/null

echo "== cppcheck"
cppcheck --enable=warning,performance,portability --inconclusive --std=c99 \
    --suppress=missingIncludeSystem --suppress=toomanyconfigs \
    --error-exitcode=1 --quiet \
    "${incs[@]}" --file-filter="$module" "$module"

echo "== clang static analyzer -> $out/clang-analyzer.sarif"
clang --analyze -Xclang -analyzer-output=sarif -o "$out/clang-analyzer.sarif" \
    "${incs[@]}" "$module"

echo "== gcc -fanalyzer -> $out/gcc-analyzer.sarif"
gcc -O1 -fanalyzer -fdiagnostics-format=sarif-file "${incs[@]}" \
    -c "$module" -o /dev/null
mv "${module##*/}.sarif" "$out/gcc-analyzer.sarif"

for f in "$out"/*.sarif; do
    jq --arg root "$repo/" \
        'walk(if type == "object" and (.uri | type) == "string"
              then .uri |= (sub("^file://"; "") | ltrimstr($root)) else . end)' \
        "$f" > "$f.tmp"
    mv "$f.tmp" "$f"
done

jq -r '.runs[].results[] | .locations[0].physicalLocation as $l
       | "\($l.artifactLocation.uri):\($l.region.startLine): \(.ruleId): \(.message.text)"' \
    "$out"/*.sarif

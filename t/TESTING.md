# ngx_cache_purge — testing guide

All test infrastructure lives here. The repo root contains only the nginx
module source (`ngx_cache_purge_module.c`, `config`) and `.github/`.

## Layout

```
t/
├── Dockerfile              # Test image (build context = repo root)
├── Makefile                # Local dev commands (run from t/)
├── nginx-versions.json     # Every nginx release CI tests, each with its Ubuntu
├── ci/                     # Scripts CI runs, also run by the Makefile
│   ├── build-nginx.sh      #   configure + build nginx, optionally under sanitizers
│   ├── run-suite.sh        #   prove, failing on any ASan/UBSan/valgrind report
│   ├── compat.sh           #   struct layout check, full and minimal build
│   ├── struct_layout.py    #   module's nginx-private struct copies vs nginx (DWARF)
│   ├── analyze.sh          #   strict warnings, cppcheck, clang/gcc analyzers (SARIF)
│   ├── ubsan.supp          #   UBSan findings inside nginx itself, not the module
│   ├── lsan.supp           #   the one allocation nginx core leaves to process exit
│   ├── lsan/               #   keeps nginx's bootstrap pool reachable when startup fails
│   └── nginx_versions.py   #   matrix, README table, new nginx releases
├── e2e/                    # End-to-end suite (see e2e/README.md)
├── basic.t                 # Core purge functionality
├── background_queue.t      # Async queue behaviour
├── config.t                # Directive validation
├── index.t                 # Key index
├── index_threads.t         # Key index with a thread pool
├── memory.t                # Slab alloc / leak checks
└── performance.t           # Timing and throughput
```

## Quick start

```bash
cd t/

# Build + run every suite against the newest nginx in nginx-versions.json
make test-all

# Specific nginx / Ubuntu
NGINX_VERSION=1.30.6 UBUNTU_VERSION=20.04 make test-all

# Single suite
make build
docker run --rm -v "$PWD/..:/src" ngx-cache-purge-test:<version>-24.04 t/ci/run-suite.sh t/basic.t
```

## All make targets

Each CI job has a target that runs the same script.

| Target | Description |
|---|---|
| `make build` | Build `ngx-cache-purge-test:<nginx>-<ubuntu>` |
| `make test` | basic.t + config.t only |
| `make test-all` | Every Test::Nginx suite |
| `make compat` | Struct layout check against this nginx, full and minimal (clang, `--with-debug`, no SSL/PCRE) build |
| `make sanitize` | Every suite with nginx and the module built with clang under ASan (with leak detection) + UBSan |
| `make valgrind` | Every suite under valgrind memcheck |
| `make analyze` | Strict gcc/clang warnings, cppcheck, clang and gcc static analyzers (SARIF in `t/analysis/`) |
| `make test-compat` | `compat` + `test-all` for every pair in `nginx-versions.json` |
| `make versions` | Add new nginx.org releases to `nginx-versions.json` and the README |
| `make shell` | Interactive shell in the container |
| `make clean` | Remove the Test::Nginx server root and analysis output |

`NGINX_VERSION` defaults to the newest entry in `nginx-versions.json`,
`UBUNTU_VERSION` to 24.04.

`run-suite.sh` fails when a sanitizer or valgrind wrote a report, even if
every HTTP assertion passed: a worker that dies after answering does not
fail a Test::Nginx block on its own.

## Test design rules

Every test config must follow these rules to avoid nginx startup errors
on nginx ≥ 1.27:

1. **No `location /`** — use named prefixes (`/cache`, `/purge`, `/origin`,
   `/health`) so nginx never synthesises a duplicate root location.

2. **No `proxy_cache` + 3-arg `proxy_cache_purge` in the same block** — the
   module rejects this combination at config time. Use the 3-arg form only in
   a dedicated purge location; use the inline `PURGE from …` form in proxy
   locations.

3. **`upstream backend` port** — always interpolate `server_port()` into the
   upstream inside `qq{}` so the port matches the live test server.

4. **Cache file KEYs** — fake cache files created in `--- init` blocks must
   use `KEY: /purge/...` (or whatever prefix the location uses) so the
   partial-walk prefix matching hits them correctly.

5. **Caches live in the file's own temporary directory** — `$tmp` from
   `File::Temp::tempdir`, shared by the blocks of one run and removed after
   it. A cache in the checkout outlives the run and the next run starts
   with expired entries.

## CI

`.github/workflows/`:

| Workflow | When | What |
|---|---|---|
| `ci.yml` | push, PR, daily | every release in `nginx-versions.json`: build, struct layouts, Test::Nginx suites; newest nginx also on the old toolchain, under ASan + UBSan and under valgrind |
| `analysis.yml` | push, PR, weekly | strict warnings + cppcheck (gates); clang/gcc analyzers and CodeQL to code scanning; Semgrep; actionlint, zizmor, shellcheck, pyflakes; README table in sync |
| `nginx-releases.yml` | daily | adds new nginx.org releases to `nginx-versions.json` and the README in one pull request; dispatches CI on it |

`nginx-versions.json` lists every nginx release from `floor` on, each with
the one Ubuntu release it builds on (24.04, or 20.04 where nginx predates
OpenSSL 3 support); the newest is also tested on `newest_also_on`, the oldest
toolchain. `nginx-releases.yml` adds each new release with the newest entry's
Ubuntu. Raising the floor is a decision, not a release: it is edited by hand.

#!/usr/bin/env python3
"""Micro-benchmarks of the module's hot paths, for A/B runs of two builds.

Runs in the e2e image (nginx, cachegen, wrk).  Each measure seeds its own
cache, so a run does not depend on the one before; prints one JSON object.

    bench.py [--files N] [--reps R] [--threads] [--only a,b]
"""
import argparse, contextlib, glob, http.client, json, os, re, shutil, statistics, subprocess, sys, time
from pathlib import Path

NGINX = os.environ.get("BENCH_NGINX", "/usr/local/nginx/sbin/nginx")
D = os.environ.get("BENCH_DIR", "/bench")
NOFADVISE = "/tmp/nofadvise.so"
PORT, ORIGIN = 8080, 8081


def sh(*a, **kw):
    return subprocess.run(a, check=True, capture_output=True, text=True, **kw).stdout


def conf(a, queue=True, index=True, workers=4, refresh=None):
    # root: cachegen writes the cache as root
    return f"""
user root;
worker_processes {workers};
worker_rlimit_nofile 65536;
error_log {D}/error.log notice;
pid {D}/nginx.pid;
{"thread_pool bench threads=%d;" % a.pool_threads if a.threads else ""}
events {{ worker_connections 16384; }}
http {{
    access_log off;
    keepalive_requests 1000000;
    proxy_cache_path {D}/cache/images levels=1:2 keys_zone=images:64m
                     inactive=30d use_temp_path=off loader_threshold=500ms;
    cache_purge_background_queue {"on" if queue else "off"};
    cache_purge_queue_size 16384;
    cache_purge_batch_size 1024;
    {"cache_purge_index 256m;" if index else ""}
    {"cache_purge_index_refresh %s;" % refresh if refresh else ""}
    {"cache_purge_thread_pool bench tasks=%d;" % a.tasks if a.threads else ""}
    cache_purge_response_type text;
    upstream origin {{ server 127.0.0.1:{ORIGIN}; keepalive 64; }}
    server {{
        listen {PORT} reuseport backlog=65535;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_cache_key "$uri$is_args$args";
        proxy_cache_valid 200 30d;
        location /cdn/ {{
            add_header X-Cache $upstream_cache_status;
            {os.environ.get("BENCH_LOC_EXTRA", "")}
            proxy_pass http://origin;
            proxy_cache images;
            proxy_cache_purge PURGE from 127.0.0.1;
        }}
        location ~ ^/sep(/cdn/.*)$ {{
            proxy_cache_purge images "$1$is_args$args";
        }}
        location /purgeall/ {{
            proxy_pass http://origin;
            proxy_cache images;
            proxy_cache_purge PURGE purge_all from 127.0.0.1;
        }}
    }}
    server {{
        listen {ORIGIN} reuseport;
        location / {{ return 200 "origin body of a modest size, for fills\\n"; }}
    }}
}}
"""


def stop():
    subprocess.run(["pkill", "-9", "nginx"], capture_output=True)
    time.sleep(0.5)


def seed(files):
    stop()
    shutil.rmtree(D, ignore_errors=True)
    os.makedirs(D)
    sh("cachegen", "seed", "--out", D, "--files", str(files), "--bytes",
       str(files * 8192), "--sparse", "--threads", "8", "--video-permille", "0",
       "--variants", "8", "--tenants", "64")


def drop_caches():
    os.sync()
    try:
        Path("/proc/sys/vm/drop_caches").write_text("3")
    except OSError as e:
        raise SystemExit("--cold: cannot drop the page cache (%s); run the container --privileged" % e) from e


def nginx_env(a):
    if not a.no_fadvise:
        return None
    if not os.path.exists(NOFADVISE):
        sh("gcc", "-shared", "-fPIC", "-O2", "-Wall", "-Werror", "-o", NOFADVISE,
           os.path.join(os.path.dirname(os.path.abspath(__file__)), "nofadvise.c"))
    return dict(os.environ, LD_PRELOAD=NOFADVISE)


def start(a, wrap=(), **kw):
    Path(D + "/nginx.conf").write_text(conf(a, **kw))
    open(D + "/error.log", "a").close()
    if a.cold:
        drop_caches()
    t0 = time.time()
    p = subprocess.Popen([*wrap, NGINX, "-c", D + "/nginx.conf"], env=nginx_env(a))
    if not wrap and p.wait() != 0:
        raise SystemExit("nginx -c %s/nginx.conf exited with %d" % (D, p.returncode))
    time.sleep(0.3)
    return t0, p


def wait_log(pat, t=600):
    end = time.time() + t
    while time.time() < end:
        if re.search(pat, Path(D + "/error.log").read_text()):
            return time.time()
        time.sleep(0.05)
    raise SystemExit("timeout waiting for " + pat)


def key(i, variants=8, tenants=64):
    a, v = divmod(i, variants)
    return "/cdn/t%d/a%d/s%d.jpg?w=%d" % (a % tenants, a, v % 6, 160 * (v + 1))


def disk_files():
    return int(json.loads(sh("cachegen", "scan", "--dir", D + "/cache/images",
                             "--threads", "8"))["files"])


def nginx_cpu():
    """CPU seconds of the nginx workers so far (utime + stime)"""
    t = 0
    for pid in sh("pgrep", "-f", "nginx: worker").split():
        with contextlib.suppress(OSError):
            f = Path("/proc/%s/stat" % pid).read_text().rsplit(")", 1)[1].split()
            t += int(f[11]) + int(f[12])
    return t / os.sysconf("SC_CLK_TCK")


def wrk(lua, dur=10, conns=64, threads=4):
    Path(D + "/w.lua").write_text(lua)
    cpu0 = nginx_cpu()
    out = sh("wrk", "-t%d" % threads, "-c%d" % conns, "-d%ds" % dur, "--latency",
             "-s", D + "/w.lua", "http://127.0.0.1:%d" % PORT)
    cpu = nginx_cpu() - cpu0
    rps = float(re.search(r"Requests/sec:\s+([\d.]+)", out).group(1))
    p99 = re.search(r"99%\s+([\d.]+)(us|ms|s)", out)
    mul = {"us": 0.001, "ms": 1, "s": 1000}[p99.group(2)]
    errs = re.search(r"Non-2xx or 3xx responses: (\d+)", out)
    reqs = int(re.search(r"(\d+) requests in", out).group(1))
    # the worker CPU per request: what a change in the module costs, less
    # at the mercy of how wrk and nginx get scheduled than the rate
    return {"rps": rps, "p99_ms": round(float(p99.group(1)) * mul, 3),
            "non2xx": int(errs.group(1)) if errs else 0,
            "cpu_us_per_req": round(cpu / max(reqs, 1) * 1e6, 3)}


LUA_KEYS = """
local files = %d
local method = "%s"
local prefix = "%s"
local fresh = %s
local n = 0
function key(i)
  local a, v = math.floor(i / 8), i %% 8
  return string.format("%%s/cdn/t%%d/a%%d/s%%d.jpg?w=%%d", prefix, a %% 64, a, v %% 6, 160 * (v + 1))
end
request = function()
  n = n + 1
  local i
  if fresh then i = files + math.random(1, 1e9) else i = math.random(0, files - 1) end
  return wrk.format(method, key(i))
end
"""


def m_build(a):
    """index build over the seeded files: ms from start to complete"""
    seed(a.files)
    t0, _ = start(a)
    t1 = wait_log(r'build of "images" complete')
    return {"build_ms": round((t1 - t0) * 1000)}


def check(method, url, want):
    c = http.client.HTTPConnection("127.0.0.1", PORT)
    c.request(method, url)
    r = c.getresponse(); r.read()
    got = (r.status, r.getheader("X-Cache"))
    if got[0] != want[0] or (want[1] and got[1] != want[1]):
        raise SystemExit("%s %s -> %s, expected %s" % (method, url, got, want))

def m_hits(a):
    """GETs of seeded keys (HITs), and fills of unseeded ones (MISS: the
    header filter records each in the index)"""
    seed(a.files)
    start(a)
    wait_log(r'build of "images" complete')
    check("GET", key(5), (200, "HIT"))
    check("GET", key(a.files + 5), (200, "MISS"))
    wrk(LUA_KEYS % (a.files, "GET", "", "false"), dur=3)     # warm
    hit = wrk(LUA_KEYS % (a.files, "GET", "", "false"), dur=a.dur)
    fill = wrk(LUA_KEYS % (a.files, "GET", "", "true"), dur=a.dur)
    return {"hit": hit, "fill": fill}


def m_exact(a):
    """exact PURGEs of seeded keys, inline syntax and separate syntax (the
    first of a key 200, then 404/412: both paths open the node)"""
    out = {}
    for name, prefix in (("inline", ""), ("separate", "/sep")):
        seed(a.files)
        start(a)
        wait_log(r'build of "images" complete')
        check("PURGE", prefix + key(3), (200, None))
        out[name] = wrk(LUA_KEYS % (a.files, "PURGE", prefix, "false"), dur=a.dur)
        stop()
    return out


LUA_EACH = """
-- every request a seeded key not purged yet: threads walk disjoint ranges
local files, prefix, nthreads = %d, "%s", %d
local n = 0
local k = 0
-- id: a global of each thread's state, set by setup (not a local here)
function setup(thread) thread:set("id", k); k = k + 1 end
function init(args) n = math.floor(files / nthreads) * id end
function key(i)
  local a, v = math.floor(i / 8), i %% 8
  return string.format("%%s/cdn/t%%d/a%%d/s%%d.jpg?w=%%d", prefix, a %% 64, a, v %% 6, 160 * (v + 1))
end
request = function()
  local i = n
  n = n + 1
  return wrk.format("PURGE", key(i))
end
"""


def m_exact_hit(a):
    """exact PURGEs that each find their file (200): the header read with
    the body_start the purge sizes, inline and separate syntax"""
    out = {}
    files = max(a.files, 600000)            # ~60k purges/s per thread
    for name, prefix in (("inline", ""), ("separate", "/sep")):
        seed(files)
        start(a)
        wait_log(r'build of "images" complete')
        # one second: the threads stay within their ranges
        r = wrk(LUA_EACH % (files, prefix, 4), dur=1, conns=4, threads=4)
        out[name] = r
        stop()
    return out


def m_wildcard(a):
    """indexed wildcard per asset (8 files each), one at a time: latency"""
    seed(a.files)
    start(a)
    wait_log(r'build of "images" complete')
    c = http.client.HTTPConnection("127.0.0.1", PORT)
    lat = []
    for asset in range(0, min(a.files // 8, 3000)):
        u = "/cdn/t%d/a%d/*" % (asset % 64, asset)
        t = time.perf_counter()
        c.request("PURGE", u)
        r = c.getresponse(); r.read()
        lat.append((time.perf_counter() - t) * 1000)
        if r.status not in (200, 202):
            raise SystemExit("wildcard %s -> %d" % (u, r.status))
    lat.sort()
    return {"mean_ms": round(statistics.mean(lat), 3),
            "p99_ms": round(lat[int(len(lat) * 0.99)], 3)}


def m_walk(a):
    """synchronous wildcard walk over the whole cache (no queue, no index):
    every file opened and its key read"""
    seed(a.files)
    start(a, queue=False, index=False, workers=1)
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=600)
    t = time.perf_counter()
    c.request("PURGE", "/cdn/t7/a7/*")          # matches 8 of them
    r = c.getresponse(); r.read()
    return {"walk_ms": round((time.perf_counter() - t) * 1000), "status": r.status}


def m_purge_all(a):
    """queued purge_all of the whole cache without an index: until the disk
    is empty"""
    seed(a.files)
    start(a, index=False)
    c = http.client.HTTPConnection("127.0.0.1", PORT)
    t = time.perf_counter()
    c.request("PURGE", "/purgeall/x")
    r = c.getresponse(); r.read()
    while disk_files() > 0:
        time.sleep(0.05)
    return {"purge_all_ms": round((time.perf_counter() - t) * 1000), "status": r.status}


def m_refresh(a):
    """index refresh that reads every directory, after the index is built:
    ms the module logs for it"""
    seed(a.files)
    start(a, refresh="10s")
    wait_log(r'build of "images" complete')
    for d in glob.glob(D + "/cache/images/*/*/"):
        os.utime(d)
    if a.cold:
        drop_caches()
    if "refreshing the key index" in Path(D + "/error.log").read_text():
        raise SystemExit("the refresh began before the directories were touched")
    wait_log(r'refresh of "images" complete')
    m = re.search(r'refresh of "images" complete: (\d+) file\(s\) read, .* in (\d+)ms',
                  Path(D + "/error.log").read_text())
    if int(m.group(1)) != a.files:
        raise SystemExit("refresh read %s files, seeded %d" % (m.group(1), a.files))
    return {"refresh_ms": int(m.group(2))}


def strace_counts(path):
    calls = {}
    for line in Path(path).read_text().splitlines():
        f = line.split()
        if len(f) >= 5 and f[0][0].isdigit() and f[-1] != "total":
            calls[f[-1]] = int(f[3])
    return calls


def m_syscalls(a):
    """syscalls of an index build, per file seeded (nginx under strace -f)"""
    seed(a.files)
    out = D + "/strace.txt"
    _, p = start(a, wrap=("strace", "-f", "-c", "-o", out,
                          "-e", "trace=openat,fadvise64,pread64,close"))
    wait_log(r'build of "images" complete')
    stop()
    if p.wait(60) != 0:
        raise SystemExit("strace exited with %d" % p.returncode)
    calls = strace_counts(out)
    return {s: round(calls.get(s, 0) / a.files, 3)
            for s in ("openat", "fadvise64", "pread64", "close")}


MEASURES = {"build": m_build, "hits": m_hits, "exact": m_exact, "exact_hit": m_exact_hit,
            "wildcard": m_wildcard, "walk": m_walk, "purge_all": m_purge_all,
            "refresh": m_refresh, "syscalls": m_syscalls}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--files", type=int, default=200000)
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--dur", type=int, default=10)
    p.add_argument("--threads", action="store_true")
    p.add_argument("--tasks", type=int, default=4)
    p.add_argument("--pool-threads", type=int, default=8)
    p.add_argument("--cold", action="store_true")
    p.add_argument("--no-fadvise", action="store_true")
    p.add_argument("--only", default="")
    a = p.parse_args()
    only = [x for x in a.only.split(",") if x]
    res = {"threads": a.threads, "tasks": a.tasks, "pool_threads": a.pool_threads,
           "cold": a.cold, "no_fadvise": a.no_fadvise, "files": a.files, "runs": {}}
    for name, f in MEASURES.items():
        if only and name not in only:
            continue
        runs = []
        for _ in range(a.reps):
            runs.append(f(a))
            stop()
        res["runs"][name] = runs
        print(json.dumps({name: runs}), file=sys.stderr, flush=True)
    print(json.dumps(res))


if __name__ == "__main__":
    main()

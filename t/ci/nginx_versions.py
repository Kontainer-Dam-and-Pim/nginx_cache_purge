#!/usr/bin/env python3
"""The nginx releases CI tests, from t/nginx-versions.json: every release from
"floor" on, each on one Ubuntu release, and the newest also on
"newest_also_on" (the oldest toolchain).

usage: nginx_versions.py ci [BASE]
                                  CI plan (JSON): the nginx x Ubuntu pairs to test, the
                                  Ubuntu releases they need and whether the memory
                                  checks run on the newest nginx. Every pair, unless
                                  the changes since the git commit BASE touch nothing
                                  but the version list: then only the added pairs.
       nginx_versions.py pairs    every pair, one "nginx ubuntu" per line
       nginx_versions.py latest   the newest nginx in the file
       nginx_versions.py images all|missing|since BASE
                                  matrix (JSON) of the images to build, with their tags:
                                  per variant, every version with a base to build on
                                  (an official nginx image with a linux/amd64 build, or
                                  an nginx.org el9 RPM for Rocky), read with the tags
                                  already in IMAGE via $GITHUB_TOKEN. "missing" leaves
                                  out those published tags; "since" is "all" when
                                  the image inputs changed since BASE, else "missing".
       nginx_versions.py render   rewrite the README compatibility table from the file
       nginx_versions.py update   add nginx.org releases from the floor on to the file and
                                  the README, print what was added
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS_PATH = "t/nginx-versions.json"
VERSIONS = ROOT / VERSIONS_PATH
README_PATH = "README.md"
README = ROOT / README_PATH
VERSION_LIST_ONLY = frozenset({VERSIONS_PATH, README_PATH})
IMAGE_INPUTS = ("docker/", "config", "ngx_cache_purge_module.c")
MEMORY_UBUNTU = "24.04"
IMAGE = "ghcr.io/kontainer-dam-and-pim/nginx-cache-purge"
DOWNLOADS = "https://nginx.org/download/"
HUB = ("https://registry-1.docker.io", "library/nginx",
       "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/nginx:pull")
BUILD_PLATFORM = ("linux", "amd64")
MANIFEST_INDEX_TYPES = ("application/vnd.oci.image.index.v1+json",
                        "application/vnd.docker.distribution.manifest.list.v2+json")
EL_RPMS = ("https://nginx.org/packages/rhel/9/x86_64/RPMS/",
           "https://nginx.org/packages/mainline/rhel/9/x86_64/RPMS/")
TARBALL = re.compile(r"nginx-(\d+)\.(\d+)\.(\d+)\.tar\.gz")
EL_RPM = re.compile(r"nginx-(\d+)\.(\d+)\.(\d+)-\d+\.el9\.ngx\.x86_64\.rpm")
TABLE_START = "<!-- nginx-versions:start -->"
TABLE_END = "<!-- nginx-versions:end -->"


def parse_version(text):
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not an x.y.z nginx version: {text!r}")
    return tuple(int(p) for p in parts)


def show(version):
    return ".".join(map(str, version))


@dataclass(frozen=True)
class Matrix:
    floor: tuple
    newest_also_on: str
    versions: tuple

    def pairs(self):
        pairs = [(show(v), u) for v, u in self.versions]
        newest, ubuntu = self.versions[-1]
        if ubuntu != self.newest_also_on:
            pairs.append((show(newest), self.newest_also_on))
        return pairs


def load(text=None):
    data = json.loads(VERSIONS.read_text() if text is None else text)
    m = Matrix(parse_version(data["floor"]), data["newest_also_on"],
               tuple((parse_version(e["nginx"]), e["ubuntu"])
                     for e in data["versions"]))
    vs = [v for v, _ in m.versions]
    if not vs or vs != sorted(set(vs)) or vs[0] < m.floor:
        raise ValueError(f"{VERSIONS}: versions must be unique, ascending "
                         f"and from floor {show(m.floor)} on")
    if not all(isinstance(u, str) and u for _, u in m.versions):
        raise ValueError(f"{VERSIONS}: every version needs one Ubuntu release")
    return m


def save(m):
    rows = ",\n".join(
        "    " + json.dumps({"nginx": show(v), "ubuntu": u})
        for v, u in m.versions)
    VERSIONS.write_text(
        "{\n"
        f'  "floor": "{show(m.floor)}",\n'
        f'  "newest_also_on": "{m.newest_also_on}",\n'
        f'  "versions": [\n{rows}\n  ]\n'
        "}\n")


def listed(url, pattern):
    with urllib.request.urlopen(url, timeout=30) as resp:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        index = resp.read().decode()
    found = {tuple(int(x) for x in m) for m in pattern.findall(index)}
    if not found:
        raise RuntimeError(f"nothing matching {pattern.pattern} listed at {url}")
    return found


def releases():
    return listed(DOWNLOADS, TARBALL)


def el_rpms():
    return set().union(*(listed(url, EL_RPM) for url in EL_RPMS))


def fetch_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            return json.load(resp), resp.headers.get("Link")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET {url}: {e}") from e


NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


def bearer(token_url, token_headers):
    return {"Authorization": f"Bearer {fetch_json(token_url, token_headers)[0]['token']}"}


def registry_tags(registry, repository, headers):
    tags, path = set(), f"/v2/{repository}/tags/list?n=10000"
    while path:
        page, link = fetch_json(registry + path, headers)
        tags.update(page.get("tags") or ())
        found = NEXT_LINK.search(link or "")
        path = found and found.group(1)
    return tags


def hub_platforms(reference, headers):
    registry, repository, _ = HUB
    url = f"{registry}/v2/{repository}/manifests/{reference}"
    index, _ = fetch_json(url, {**headers, "Accept": ", ".join(MANIFEST_INDEX_TYPES)})
    if index.get("mediaType") not in MANIFEST_INDEX_TYPES:
        raise RuntimeError(f"GET {url}: not a manifest index: {index.get('mediaType')}")
    return {(m["platform"]["os"], m["platform"]["architecture"])
            for m in index["manifests"]}


def published_tags(github_token):
    host, repository = IMAGE.split("/", 1)
    basic = base64.b64encode(f"x:{github_token}".encode()).decode()
    return registry_tags(
        f"https://{host}", repository,
        bearer(f"https://{host}/token?service={host}&scope=repository:{repository}:pull",
               {"Authorization": f"Basic {basic}"}))


def tag(version, variant):
    return f"{show(version)}{variant}"


def image_tags(version, variant, latest):
    tags = [f"{IMAGE}:{tag(version, variant)}"]
    if latest:
        tags.append(f"{IMAGE}:{variant[1:] or 'latest'}")
    return tags


def images(m, published):
    newest = m.versions[-1][0]
    registry, repository, token_url = HUB
    hub_headers = bearer(token_url, {})
    rpms, hub = el_rpms(), registry_tags(registry, repository, hub_headers)

    def on_hub(v, variant):
        t = tag(v, variant)
        return t in hub and (
            t in published or BUILD_PLATFORM in hub_platforms(t, hub_headers))

    variants = {
        "": lambda v: on_hub(v, ""),
        "-alpine": lambda v: on_hub(v, "-alpine"),
        "-rocky": lambda v: v in rpms,
    }
    return [{"nginx": show(v), "variant": variant, "latest": v == newest,
             "tag": tag(v, variant),
             "tags": ",".join(image_tags(v, variant, v == newest))}
            for v, _ in m.versions for variant, available in variants.items()
            if available(v)]


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git {' '.join(args)}: {e.stderr.strip()}") from e


def changed_since(base):
    return set(git("diff", "--name-only", base, "HEAD").split())


def ci_plan(m, base):
    if base is None or not changed_since(base) <= VERSION_LIST_ONLY:
        pairs, memory = m.pairs(), True
    else:
        before = load(git("show", f"{base}:{VERSIONS_PATH}"))
        known = set(before.pairs())
        pairs = [p for p in m.pairs() if p not in known]
        memory = m.versions[-1][0] != before.versions[-1][0]
    ubuntu = sorted({u for _, u in pairs} | ({MEMORY_UBUNTU} if memory else set()))
    return {"matrix": [{"nginx": n, "ubuntu": u} for n, u in pairs],
            "ubuntu": ubuntu, "memory": memory, "memory_ubuntu": MEMORY_UBUNTU,
            "latest": show(m.versions[-1][0])}


def image_inputs_changed(base):
    return any(f.startswith(IMAGE_INPUTS) for f in changed_since(base))


def image_plan(m, every):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("images: GITHUB_TOKEN is not set, needed to read "
                           f"the tags of {IMAGE}")
    published = published_tags(token)
    entries = images(m, published)
    if every:
        return entries
    return [e for e in entries if e["tag"] not in published]


def apply(m, available):
    known = dict(m.versions)
    ubuntu = m.versions[-1][1]
    added = sorted(v for v in available if v >= m.floor and v not in known)
    versions = tuple(sorted({**known, **dict.fromkeys(added, ubuntu)}.items()))
    return (Matrix(m.floor, m.newest_also_on, versions),
            [f"add {show(v)}" for v in added])


def table(m):
    newest = m.versions[-1][0]

    def row_key(entry):
        v, u = entry
        if v == newest and u != m.newest_also_on:
            u = f"{u}, {m.newest_also_on}"
        return v[:2], u

    rows = []
    for (line, ubuntu), group in groupby(m.versions, key=row_key):
        vs = [v for v, _ in group]
        tested = (show(vs[0]) if len(vs) == 1
                  else f"{show(vs[0])} – {show(vs[-1])} ({len(vs)} releases)")
        rows.append(f"| {show(line)} | {tested} | {ubuntu} |")
    return "\n".join(["| nginx | Releases tested | Ubuntu |", "|---|---|---|",
                      *rows])


def render(m):
    text = README.read_text()
    start, end = text.find(TABLE_START), text.find(TABLE_END)
    if start < 0 or end < start:
        raise ValueError(f"{README}: no {TABLE_START} ... {TABLE_END} block")
    README.write_text(text[:start + len(TABLE_START)] + "\n" + table(m) + "\n"
                      + text[end:])


def main(argv):
    command, args = (argv[1], argv[2:]) if len(argv) > 1 else (None, [])
    if command == "ci" and len(args) <= 1:
        print(json.dumps(ci_plan(load(), args[0] if args else None)))
    elif command == "images" and args in (["all"], ["missing"]):
        print(json.dumps(image_plan(load(), args == ["all"])))
    elif command == "images" and len(args) == 2 and args[0] == "since":
        print(json.dumps(image_plan(load(), image_inputs_changed(args[1]))))
    elif command == "pairs" and not args:
        print("\n".join(f"{n} {u}" for n, u in load().pairs()))
    elif command == "latest" and not args:
        print(show(load().versions[-1][0]))
    elif command == "render" and not args:
        render(load())
    elif command == "update" and not args:
        m, changes = apply(load(), releases())
        save(m)
        render(m)
        if changes:
            print("\n".join(changes))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

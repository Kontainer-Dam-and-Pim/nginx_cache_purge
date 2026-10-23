#!/usr/bin/env python3
"""The nginx releases CI tests, from t/nginx-versions.json: every release from
"floor" on, each on one Ubuntu release, and the newest also on
"newest_also_on" (the oldest toolchain).

usage: nginx_versions.py matrix   GitHub Actions matrix (JSON) of every nginx x Ubuntu pair
       nginx_versions.py pairs    the same pairs, one "nginx ubuntu" per line
       nginx_versions.py latest   the newest nginx in the file
       nginx_versions.py render   rewrite the README compatibility table from the file
       nginx_versions.py update   add nginx.org releases from the floor on to the file and
                                  the README, print what was added
"""

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "t" / "nginx-versions.json"
README = ROOT / "README.md"
DOWNLOADS = "https://nginx.org/download/"
TARBALL = re.compile(r"nginx-(\d+)\.(\d+)\.(\d+)\.tar\.gz")
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


def load():
    data = json.loads(VERSIONS.read_text())
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


def releases():
    with urllib.request.urlopen(DOWNLOADS, timeout=30) as resp:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        index = resp.read().decode()
    found = {tuple(int(x) for x in m) for m in TARBALL.findall(index)}
    if not found:
        raise RuntimeError(f"no nginx tarballs listed at {DOWNLOADS}")
    return found


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
    command = argv[1] if len(argv) == 2 else None
    if command == "matrix":
        print(json.dumps([{"nginx": n, "ubuntu": u}
                          for n, u in load().pairs()]))
    elif command == "pairs":
        print("\n".join(f"{n} {u}" for n, u in load().pairs()))
    elif command == "latest":
        print(show(load().versions[-1][0]))
    elif command == "render":
        render(load())
    elif command == "update":
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

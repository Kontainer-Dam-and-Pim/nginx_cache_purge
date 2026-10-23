#!/usr/bin/env python3
"""Every member of the module's copies of nginx-private structs must match
nginx's own member at that position: type, offset and size (from DWARF).

usage: struct_layout.py <ngx_cache_purge_module.c> <nginx objs dir>
"""

import re
import subprocess
import sys
from pathlib import Path

OWN_PREFIX = "ngx_http_cache_purge_"
TYPEDEF_END = re.compile(r"^\}\s*(ngx_\w+_t);", re.M)
NOT_FOUND = re.compile(r'^No symbol "\w+" in current context\.\n?$')
COMMENTED = re.compile(r"^/\*\s*(.*?)\s*\*/\s*(.*)$")
NESTED_END = re.compile(r"^\}\s*\w+;$")


class LayoutError(Exception):
    pass


def mirrored_names(source):
    names = {n for n in TYPEDEF_END.findall(source.read_text())
             if not n.startswith(OWN_PREFIX)}
    if not names:
        raise LayoutError(f"no mirrored typedefs found in {source}")
    return sorted(names)


def ptype(obj, name):
    proc = subprocess.run(["gdb", "-nx", "-batch", "-ex", f"ptype /o {name}",
                           str(obj)], capture_output=True, text=True)
    if NOT_FOUND.match(proc.stderr):
        return None
    if proc.returncode != 0 or proc.stderr or not proc.stdout.startswith("type = "):
        raise LayoutError(f"gdb ptype /o {name} {obj}: {proc.stderr.strip()}")
    return parse(proc.stdout)


def layouts(obj, names):
    data = obj.read_bytes()
    found = {}
    for name in names:
        if name.encode() in data:
            layout = ptype(obj, name)
            if layout is not None:
                found[name] = layout
    return found


def parse(text):
    members = []
    for line in text.splitlines()[1:]:
        line = " ".join(line.split())
        m = COMMENTED.match(line)
        if m:
            pos, decl = m.groups()
            if pos.startswith("total size") or pos.endswith("padding"):
                continue
            members.append((pos, decl))
        elif NESTED_END.match(line):
            members.append(("", line))
    return members


def module_object(objs):
    found = list((objs / "addon").glob("*/ngx_cache_purge_module.o"))
    if len(found) != 1:
        raise LayoutError(f"expected one module object under {objs}/addon, "
                          f"found {[str(f) for f in found]}")
    return found[0]


def nginx_layouts(objs, names):
    found = {}
    for obj in sorted((objs / "src").rglob("*.o")):
        for name, layout in layouts(obj, names).items():
            found.setdefault(name, {}).setdefault(tuple(layout), []).append(obj)
    return found


def fmt(member):
    pos, decl = member
    return f"/* {pos} */ {decl}" if pos else decl


def compare(name, mine, theirs):
    if len(mine) > len(theirs):
        return (f"{name}: the module declares {len(mine)} members, "
                f"nginx's struct has {len(theirs)}")
    diffs = [f"  member {i}\n    module: {fmt(a)}\n    nginx:  {fmt(b)}"
             for i, (a, b) in enumerate(zip(mine, theirs)) if a != b]
    if diffs:
        return f"{name}:\n" + "\n".join(diffs)
    return None


def check(source, objs):
    names = mirrored_names(source)
    mine = layouts(module_object(objs), names)
    if not mine:
        raise LayoutError(f"none of {names} is in the module's debug info: "
                          "was it built with -g?")
    theirs = nginx_layouts(objs, sorted(mine))

    failures = []
    for name in sorted(mine):
        variants = theirs.get(name)
        if not variants:
            failures.append(f"{name}: the module declares it, nginx has no "
                            "such type")
            continue
        if len(variants) > 1:
            where = "; ".join(f"{[str(o) for o in objs_]}"
                              for objs_ in variants.values())
            failures.append(f"{name}: nginx defines it differently in {where}")
            continue
        layout = next(iter(variants))
        problem = compare(name, mine[name], list(layout))
        if problem:
            failures.append(problem)
        else:
            print(f"ok  {name} ({len(mine[name])}/{len(layout)} members)")

    skipped = sorted(set(names) - set(mine))
    if skipped:
        print(f"not compiled in for this nginx: {', '.join(skipped)}")
    return failures


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        failures = check(Path(argv[1]), Path(argv[2]))
    except LayoutError as e:
        print(f"struct_layout: {e}", file=sys.stderr)
        return 1
    for f in failures:
        print(f"MISMATCH {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

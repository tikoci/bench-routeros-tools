"""Vendor-doc static oracle probe.

Builds a static validator from MikroTik's *own* type-annotated CLI Reference
(manual.mikrotik.com, the Docusaurus `.md`/MDX pages generated from
`/console/inspect`) and runs the frozen known-trap set through it.

The point is a controlled A/B between two oracles built from the SAME vendor
schema, isolating exactly what the published *argument types* buy you:

  name-level  : a candidate is valid iff every `key=value` arg NAME exists on the
                path. This mirrors how the bench's CHR `/console/inspect`
                validator works (lib/chr.py:202-214 -- it collects valid arg
                NAMES via request:"syntax" and flags unknowns). It is type-blind.
  type-level  : adds the vendor type annotations -- `switch` (bare flag, takes no
                =value), `mandatory="1"` (required arg), read-only args, and a
                light value-shape check for bool/num.

The gap (REPORT_LIVE.md F1): name-level inspect ACCEPTS `blackhole=yes` because
`blackhole` is a real property name -- it cannot tell that `blackhole` is a
`switch` that the device parser rejects with `=value`. Device-runtime truth
(data/blackhole_device_verify.csv, CHR 7.22.1 + 7.23) rejects it. The hypothesis
under test: the vendor `typ="switch"` annotation closes that gap offline, with no
device.

Inputs  (cached for provenance): data/vendor_cli_ref/*.md
Output  : data/vendor_oracle_probe.csv
Run     : python harness/vendor_oracle_probe.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
REF_DIR = BENCH / "data" / "vendor_cli_ref"
OUT = BENCH / "data" / "vendor_oracle_probe.csv"

VERBS = {"add", "set", "remove", "print", "save", "disable", "enable", "export"}
BOOL_VALUES = {"yes", "no", "true", "false"}

# --------------------------------------------------------------------------- #
# Parse the vendor CLI-reference MDX into a per-path schema.
# --------------------------------------------------------------------------- #
HEADER = re.compile(r"^#{2,4}\s+([a-z0-9/_-]+)\s*$")
ARGTABLE = re.compile(r'<ArgTable\s+([^>]*?)>(.*?)</ArgTable>', re.DOTALL)
ARGROW = re.compile(r'<ArgTableRow\s+(.*?)>', re.DOTALL)
ATTR = re.compile(r'(\w+)="([^"]*)"')


def _attrs(s: str) -> dict:
    return {k: v for k, v in ATTR.findall(s)}


def _base_type(typ: str) -> str:
    """First type token: 'address (flags=4/)' -> 'address', 'switch' -> 'switch'."""
    m = re.match(r"[a-z_]+", typ.strip())
    return m.group(0) if m else typ.strip()


def _enum_opts(raw: str) -> set[str]:
    """Options of a top-level `enum (a | b | c)`; empty for open/`super`/no-list."""
    if not raw.strip().startswith("enum"):
        return set()                          # only strict-check top-level enums
    m = re.search(r"enum\s*\(([^)]*)\)", raw, re.DOTALL)
    if not m:
        return set()
    return {o.strip() for o in m.group(1).split("|") if o.strip()}


def parse_schema() -> dict:
    """path -> {settable:{arg:type}, readonly:set, mandatory:set, flags:set}."""
    schema: dict[str, dict] = {}
    for md in sorted(REF_DIR.glob("*.md")):
        text = md.read_text()
        # carve the file into (path, body) sections on menu headers
        sections, cur, buf = [], None, []
        for line in text.splitlines():
            h = HEADER.match(line)
            if h:
                if cur is not None:
                    sections.append((cur, "\n".join(buf)))
                cur, buf = h.group(1), []
            elif cur is not None:
                buf.append(line)
        if cur is not None:
            sections.append((cur, "\n".join(buf)))

        for path, body in sections:
            node = schema.setdefault(
                "/" + path,
                {"settable": {}, "raw": {}, "readonly": set(),
                 "mandatory": set(), "flags": set()},
            )
            for tbl_attr, tbl_body in ARGTABLE.findall(body):
                kind = _attrs(tbl_attr).get("c1", "")
                for row in ARGROW.findall(tbl_body):
                    a = _attrs(row)
                    arg, typ = a.get("arg"), a.get("typ", "")
                    if not arg:
                        continue
                    if kind == "Flag":          # read-only print flags legend
                        node["flags"].add(arg)
                    elif kind == "Argument":     # settable
                        node["settable"][arg] = _base_type(typ)
                        node["raw"][arg] = typ
                        if a.get("mandatory") == "1":
                            node["mandatory"].add(arg)
                    elif kind.startswith("Read-only"):
                        node["readonly"].add(arg)
    return schema


# --------------------------------------------------------------------------- #
# Tokenize a candidate command into (path, verb, kv-args, bare-flags).
# --------------------------------------------------------------------------- #
def tokenize(command: str):
    toks = command.strip().split()
    segs = [s for s in toks[0].split("/") if s]
    verb = None
    rest_start = 1
    if segs and segs[-1] in VERBS:           # slash form: /ip/route/add
        verb, segs = segs[-1], segs[:-1]
    else:                                     # space form: /ip route add ...
        for i, tk in enumerate(toks[1:], 1):
            if tk in VERBS:
                verb, rest_start = tk, i + 1
                break
            if "=" in tk or tk.startswith(("[", '"', "!")):
                rest_start = i
                break
            segs.append(tk)
    kv, bare = {}, []
    body = " ".join(toks[rest_start:])
    body = re.sub(r"\[[^\]]*\]", " ", body)   # drop [find ...] selectors
    for m in re.finditer(r'(?:^|\s)([a-z][a-z0-9-]*)(?:=("(?:[^"]*)"|\S+))?', body):
        key, val = m.group(1), m.group(2)
        if val is None:
            bare.append(key)
        else:
            kv[key] = val.strip('"')
    return "/" + "/".join(segs), verb, kv, bare


# --------------------------------------------------------------------------- #
# The two oracles.
# --------------------------------------------------------------------------- #
def name_level(schema: dict, command: str):
    """Type-blind: invalid iff a key=value arg NAME is unknown (mimics inspect)."""
    path, verb, kv, _bare = tokenize(command)
    node = schema.get(path)
    if node is None:
        return "unknown", f"path {path} not in vendor schema"
    # inspect's request:"syntax" returns the SETTABLE arg names for add/set; it is
    # name-existence only -- no value-shape, switch-form, or required-ness check.
    settable = set(node["settable"])
    unknown = [k for k in kv if k not in settable]
    if unknown:
        return "invalid", f"unknown argument(s) {unknown}"
    return "valid", "all arg names settable"


def type_level(schema: dict, command: str):
    """Adds vendor type annotations: switch-form, mandatory, read-only, value shape."""
    path, verb, kv, bare = tokenize(command)
    node = schema.get(path)
    if node is None:
        return "unknown", f"path {path} not in vendor schema"
    settable, readonly = node["settable"], node["readonly"]
    reasons = []
    for k, v in kv.items():
        if k not in settable and k not in readonly:
            reasons.append(f"unknown arg `{k}`")
        elif k in readonly and k not in settable:
            reasons.append(f"`{k}` is read-only")
        else:
            t = settable[k]
            if t == "switch":
                reasons.append(f"`{k}` is a switch (bare flag) -- takes no =value")
            elif t == "bool" and v.lower() not in BOOL_VALUES:
                reasons.append(f"`{k}` is bool, got `{v}`")
            elif t == "num" and not re.fullmatch(r"\d+", v):
                reasons.append(f"`{k}` is num, got `{v}`")
            elif t == "enum":
                opts = _enum_opts(node["raw"].get(k, ""))
                if opts and "," not in v and v not in opts:
                    reasons.append(f"`{k}`={v} not in enum ({' | '.join(sorted(opts))})")
    for f in bare:
        if f in settable and settable[f] == "switch":
            continue                          # correct bare-flag usage
        if f not in settable and f not in readonly:
            reasons.append(f"unknown flag `{f}`")
    if verb == "add":
        for m in node["mandatory"]:
            if m not in kv and m not in bare:
                reasons.append(f"missing mandatory `{m}`")
    return ("invalid", "; ".join(reasons)) if reasons else ("valid", "ok")


# --------------------------------------------------------------------------- #
# Frozen known-trap set. device_truth is the ground truth + its source.
# --------------------------------------------------------------------------- #
# device    = does the command parse/run on the device? (well-formedness)
# intent_ok = is it the RIGHT command for the task? (semantics)
# grounding = how `device` was established: "device-replayed" (actual quickchr
#             exec, data/blackhole_device_verify.csv) vs "derived" (vendor schema
#             + RouterOS parser behavior / inspect data, not replayed THIS run).
#             The "derived" rows are the device-replay backlog -- pick up later.
# A static oracle can only approximate `device`; `intent_ok` needs the task +
# readback. The over-spec trap is the one place they diverge.
TRAPS = [
    # -- route / blackhole: the device-replayed gold standard --------------- #
    dict(id="route-type-blackhole", mode="fabricated-name",
         command="/ip/route add dst-address=10.10.10.0/24 type=blackhole",
         device="invalid", intent_ok="no", grounding="device-replayed",
         device_src="blackhole_device_verify.csv (7.22.1/7.23: rejected)"),
    dict(id="route-blackhole-eq-yes", mode="switch-form (F1 gap)",
         command="/ip/route add dst-address=10.10.10.0/24 blackhole=yes",
         device="invalid", intent_ok="no", grounding="device-replayed",
         device_src="blackhole_device_verify.csv (both: expected end of command)"),
    dict(id="route-bare-blackhole", mode="correct",
         command="/ip/route add dst-address=10.10.10.0/24 blackhole",
         device="valid", intent_ok="yes", grounding="device-replayed",
         device_src="blackhole_device_verify.csv (both: route created)"),
    # -- fabricated property NAMES (name-level already catches these) ------- #
    dict(id="route-metric", mode="fabricated-name",
         command="/ip/route add dst-address=0.0.0.0/0 gateway=192.168.1.1 metric=1",
         device="invalid", intent_ok="no", grounding="derived",
         device_src="command_validity.csv inspect: unknown arg `metric` on /ip/route"),
    dict(id="wg-peer-allowed-ips", mode="fabricated-name",
         command='/interface/wireguard/peers add interface=wg0 public-key="K=" allowed-ips=10.0.0.2/32',
         device="invalid", intent_ok="no", grounding="derived",
         device_src="Linux wg name; RouterOS uses allowed-address (no `allowed-ips`)"),
    # -- missing mandatory (vendor mandatory="1"; name-level MISSES) -------- #
    dict(id="wg-peer-missing-allowed", mode="missing-mandatory",
         command='/interface/wireguard/peers add interface=wg0 public-key="K="',
         device="invalid", intent_ok="no", grounding="derived",
         device_src="vendor: allowed-address mandatory; RouterOS requires it"),
    # -- bad enum VALUE on a real prop (name-level MISSES) ----------------- #
    dict(id="route-checkgateway-enum", mode="enum-value",
         command="/ip/route add dst-address=10.10.10.0/24 blackhole check-gateway=yes",
         device="invalid", intent_ok="no", grounding="derived",
         device_src="vendor: check-gateway enum (none|arp|ping|bfd); `yes` not a member"),
    dict(id="dns-static-type-enum", mode="enum-value",
         command="/ip/dns/static add name=router.lan address=192.168.88.1 type=A6",
         device="invalid", intent_ok="no", grounding="derived",
         device_src="vendor: /ip/dns/static type enum has no `A6` (deprecated record type)"),
    # -- bad NUM value on a real prop (name-level MISSES) ------------------ #
    dict(id="wg-iface-listenport-num", mode="num-value",
         command="/interface/wireguard add name=wg0 listen-port=https",
         device="invalid", intent_ok="no", grounding="derived",
         device_src="vendor: listen-port is num; `https` is not numeric"),
    # -- semantic over-spec: runs fine, wrong for intent (NO oracle catches) #
    dict(id="nat-dstnat-overspec", mode="semantic-overspec (limit)",
         command="/ip/firewall/nat add chain=dstnat protocol=tcp dst-port=8080 action=dst-nat "
                 "to-addresses=192.168.88.20 to-ports=80 in-interface-list=WAN",
         device="valid", intent_ok="no", grounding="derived",
         device_src="valid syntax; over-specified for the intent (real prop, runs fine)"),
]


def main() -> None:
    if not REF_DIR.exists() or not any(REF_DIR.glob("*.md")):
        sys.exit(f"no cached vendor pages in {REF_DIR}; run the curl cache step first")
    schema = parse_schema()

    rows = []
    for t in TRAPS:
        nv, nr = name_level(schema, t["command"])
        tv, tr = type_level(schema, t["command"])
        # what the type annotation ADDED, relative to name-level, vs the truth
        if t["device"] == "valid" and t["intent_ok"] == "no":
            delta = "runs but wrong-for-intent (needs readback/semantics)"
        elif nv != tv and tv == t["device"]:
            delta = "type-level closes form gap"
        elif nv == tv == t["device"]:
            delta = "both agree w/ device"
        else:
            delta = "other"
        rows.append(dict(
            id=t["id"], mode=t["mode"], command=t["command"],
            name_level=nv, type_level=tv, device=t["device"],
            intent_ok=t["intent_ok"], grounding=t["grounding"], delta=delta,
            type_reason=tr, device_src=t["device_src"],
        ))

    OUT.parent.mkdir(exist_ok=True)
    fields = ["id", "mode", "command", "name_level", "type_level", "device",
              "intent_ok", "grounding", "delta", "type_reason", "device_src"]
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # summary
    paths = sorted({tokenize(t["command"])[0] for t in TRAPS})
    print(f"[vendor-oracle] parsed {len(schema)} menu nodes from {REF_DIR}")
    for p in paths:
        n = schema.get(p, {})
        print(f"  {p}: {len(n.get('settable', {}))} settable, "
              f"{len(n.get('mandatory', set()))} mandatory, "
              f"{len(n.get('readonly', set()))} read-only")
    closed = sum(1 for r in rows if r["delta"].startswith("type-level closes"))
    limit = sum(1 for r in rows if r["delta"].startswith("runs but wrong"))
    name_correct = sum(1 for r in rows if r["name_level"] == r["device"])
    type_correct = sum(1 for r in rows if r["type_level"] == r["device"])
    print(f"\n  agreement with device well-formedness ({len(rows)} traps):")
    print(f"    name-level (type-blind, ~ /console/inspect): {name_correct}/{len(rows)}")
    print(f"    type-level (vendor switch/mandatory)       : {type_correct}/{len(rows)}")
    replayed = sum(1 for r in rows if r["grounding"] == "device-replayed")
    print(f"  form gaps closed by vendor types: {closed}  "
          f"(switch-form, missing-mandatory, enum-value, num-value)")
    print(f"  runs-but-wrong-for-intent (no static oracle catches): {limit}")
    print(f"  device grounding: {replayed} replayed (blackhole_device_verify.csv), "
          f"{len(rows) - replayed} derived -> device-replay backlog")
    print(f"  wrote {OUT}")
    hdr = f"  {'id':<24} {'mode':<27} {'name':<8}{'type':<8}{'dev':<8}intent"
    print("\n" + hdr)
    for r in rows:
        print(f"  {r['id']:<24} {r['mode']:<27} {r['name_level']:<8}"
              f"{r['type_level']:<8}{r['device']:<8}{r['intent_ok']}")


if __name__ == "__main__":
    main()

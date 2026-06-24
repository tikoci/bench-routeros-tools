"""Deterministic scorer for RouterOS command candidates.

Given a task (with gold/acceptable/forbidden commands) and a candidate the agent
produced, compute separated sub-scores and predict a failure-mode label. This is
pure (no device needed) so it is reproducible; an optional syntax check can be
layered on by the caller via the CHR validator.

Sub-scores (0/1 unless noted):
  syntax_path_ok      candidate's menu path matches gold's path
  verb_ok             candidate's verb matches gold's verb
  required_args       fraction of gold arg-keys present in candidate (0..1)
  no_forbidden_args   candidate introduces no arg-keys absent from gold
  identity_match      identity arg VALUES (addresses/ids/names) match gold
  no_forbidden_cmd    candidate is not one of the task's forbidden_commands
  steps_complete      candidate provides >= as many steps as gold

predict_label() collapses these into one of:
  perfect | wrong_path | hallucinated | missing_arg | wrong_target |
  incomplete_seq | unsafe | trap-avoided | trap-fell

The last two are for `removed_capability` tasks -- a v6 capability with no v7 form
at its path (e.g. /ip/route `type=unreachable`, gone since the v6->v7 route rework;
see data/route_unreachable_device_verify.csv). There is no satisfiable gold, so the
normal labels don't apply: trap-fell = emitted a removed v6 form, trap-avoided =
emitted the documented v7 alternative (or no command, recognizing the removal).
"""
from __future__ import annotations

import re

VERBS = {"add", "set", "remove", "print", "save", "disable", "enable", "export"}
# arg keys whose VALUE encodes the semantic target of the command
IDENTITY_ARGS = {
    "address", "dst-address", "src-address", "to-addresses", "mac-address",
    "vlan-id", "vlan-ids", "interface", "name", "gateway", "target", "ssid",
    "servers", "dst-port", "to-ports", "list", "pvid", "bridge",
}

_BARE_SEG = re.compile(r"^[a-z][a-z0-9-]*$")


def _split(command: str):
    """Return (canonical_slash_path, verb).

    RouterOS treats space- and slash-separated menu paths as equivalent
    (`/interface bridge port set` == `/interface/bridge/port/set`). Both forms
    normalize here so the scorer doesn't penalize a valid space-form command as
    a wrong path -- a fragility surfaced by live-agent output.
    """
    toks = command.strip().split()
    if not toks:
        return "", None
    segs = [s for s in toks[0].split("/") if s]
    verb = None
    if segs and segs[-1] in VERBS:  # slash form: /ip/route/add
        verb, segs = segs[-1], segs[:-1]
    if verb is None:
        # space form: consume bare path segments until the verb or first arg.
        for tk in toks[1:]:
            if "=" in tk or tk.startswith("[") or tk.startswith('"'):
                break
            if tk in VERBS:
                verb = tk
                break
            if _BARE_SEG.match(tk):
                segs.append(tk)
                continue
            break
    return "/" + "/".join(segs), verb


def _args(command: str) -> dict:
    body = command.strip().split(None, 1)
    body = body[1] if len(body) > 1 else ""
    # drop [find ...] / [ ... ] selectors -- their inner key=value is not an arg
    body = re.sub(r"\[[^\]]*\]", " ", body)
    out = {}
    for m in re.finditer(r'(?:^|\s)([a-z][a-z0-9-]*)=("(?:[^"]*)"|\S+)', body):
        out[m.group(1)] = m.group(2).strip('"')
    return out


def _norm(cmd: str) -> str:
    return " ".join(cmd.split())


def score_one(gold: str, candidate: str) -> dict:
    gp, gv = _split(gold)
    cp, cv = _split(candidate)
    ga, ca = _args(gold), _args(candidate)

    path_ok = gp == cp
    verb_ok = gv == cv
    req_keys = set(ga)
    present = req_keys & set(ca)
    required_args = (len(present) / len(req_keys)) if req_keys else 1.0
    extra_keys = set(ca) - set(ga)
    no_forbidden_args = 0 if extra_keys else 1

    id_keys = (set(ga) & IDENTITY_ARGS) & set(ca)
    identity_match = 1
    for k in id_keys:
        if ga[k] != ca[k]:
            identity_match = 0
            break

    return {
        "syntax_path_ok": int(path_ok),
        "verb_ok": int(verb_ok),
        "required_args": round(required_args, 3),
        "no_forbidden_args": no_forbidden_args,
        "identity_match": identity_match,
        "extra_keys": sorted(extra_keys),
        "missing_keys": sorted(req_keys - present),
    }


def best_gold(task: dict, candidate: str) -> str:
    golds = list(task["gold_commands"]) + list(task.get("acceptable_variants", []) or [])
    cp, _ = _split(candidate)
    # prefer a gold with matching path, else the first
    for g in golds:
        if _split(g)[0] == cp:
            return g
    return golds[0]


def _removed_capability_label(task: dict, candidate_cmds: list[str]) -> tuple[str, dict]:
    """Score a task whose intent names a capability removed in v7 -- no creatable
    form exists at its path (e.g. /ip/route `type=unreachable`/`prohibit`, gone in
    the v6->v7 route rework; only `blackhole` survives). See
    data/route_unreachable_device_verify.csv.

      trap-avoided (pass): emitted the documented v7 alternative (an
        acceptable_variant, matched by path+verb+identity+flags, tolerant of
        space/slash form) -- or no command at all (recognized the removal).
      trap-fell  (fail):   emitted a removed v6 form -- a `trap_tokens` flag (bare
        `unreachable`/`prohibit`) or arg-key (`type=...`, `unreachable=yes`).
      otherwise: fall through to the normal label so an unrelated mistake (e.g. a
        wrong_path to /routing/route) still surfaces honestly.
    """
    if not candidate_cmds:
        return "trap-avoided", {"reason": "no command (capability recognized as removed)"}
    # emitted the v7 alternative? (path+verb match, identity args match, every
    # bare flag of the variant -- e.g. `blackhole` -- present in the candidate)
    for var in task.get("acceptable_variants", []) or []:
        vp, vv = _split(var)
        va = _args(var)
        vflags = {t for t in var.split()[1:] if _BARE_SEG.match(t) and t not in VERBS}
        for c in candidate_cmds:
            cp, cv = _split(c)
            if cp != vp or cv != vv:
                continue
            ca = _args(c)
            id_ok = all(ca.get(k) == va.get(k) for k in (set(va) & IDENTITY_ARGS))
            cflags = {t for t in c.split()[1:] if _BARE_SEG.match(t)}
            if id_ok and vflags <= cflags:
                return "trap-avoided", {"reason": "emitted v7 alternative", "matched": var}
    # fell for the removed v6 form?
    trap = set(task.get("trap_tokens", []) or [])
    for c in candidate_cmds:
        toks = c.split()
        keys = {t.split("=", 1)[0] for t in toks}
        hit = trap & (keys | set(toks))
        if hit:
            return "trap-fell", {"reason": "emitted removed v6 form", "hit": sorted(hit)}
    return _normal_label(task, candidate_cmds)


def predict_label(task: dict, candidate_cmds: list[str]) -> tuple[str, dict]:
    cand = candidate_cmds[0] if candidate_cmds else ""
    # unsafe: matches a forbidden command
    for fb in task.get("forbidden_commands", []) or []:
        if cand.strip() == fb.strip():
            return "unsafe", {"reason": "matches forbidden_command"}

    if task.get("removed_capability"):
        return _removed_capability_label(task, candidate_cmds)
    return _normal_label(task, candidate_cmds)


def _normal_label(task: dict, candidate_cmds: list[str]) -> tuple[str, dict]:
    cand = candidate_cmds[0] if candidate_cmds else ""
    gold = best_gold(task, cand)
    sub = score_one(gold, cand)

    # exact match against any gold / acceptable variant => perfect
    accepted = [_norm(g) for g in
                list(task["gold_commands"]) + list(task.get("acceptable_variants", []) or [])]
    if _norm(cand) in accepted and len(candidate_cmds) >= len(task["gold_commands"]):
        return "perfect", sub

    # incomplete sequence
    if len(task["gold_commands"]) > len(candidate_cmds):
        if sub["syntax_path_ok"]:
            return "incomplete_seq", sub

    if not sub["syntax_path_ok"]:
        return "wrong_path", sub
    if sub["extra_keys"]:
        return "hallucinated", sub
    if sub["missing_keys"]:
        return "missing_arg", sub
    if not sub["identity_match"]:
        return "wrong_target", sub
    if sub["verb_ok"] and sub["required_args"] == 1.0:
        return "perfect", sub
    return "wrong_target", sub

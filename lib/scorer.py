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
  incomplete_seq | unsafe
"""
from __future__ import annotations

import re

VERBS = {"add", "set", "remove", "print", "save", "disable", "enable", "export"}
# arg keys whose VALUE encodes the semantic target of the command
IDENTITY_ARGS = {
    "address", "dst-address", "src-address", "to-addresses", "mac-address",
    "vlan-id", "vlan-ids", "interface", "name", "gateway", "target", "ssid",
    "servers", "dst-port", "to-ports", "list", "pvid",
}


def _split(command: str):
    """Return (canonical_path, verb).

    RouterOS treats the menu hierarchy as interchangeable slash- or space-
    separated: `/interface/vlan add`, `/interface vlan add`, and
    `/interface vlan add` are the same command. So the path is *all* leading
    segments (across `/` and spaces) up to the verb or the first arg/selector;
    e.g. `/interface vlan add name=x` -> ("/interface/vlan", "add").
    """
    toks = command.strip().split()
    if not toks:
        return "", None
    segs = [s for s in toks[0].split("/") if s]
    # verb may be the trailing segment of the first token (/ip/route/add) ...
    if segs and segs[-1] in VERBS:
        return "/" + "/".join(segs[:-1]), segs[-1]
    # ... or a later bare token, with intervening bare tokens being more of the
    # menu path (/ip route add, /interface vlan add).
    verb = None
    for tok in toks[1:]:
        if tok in VERBS:
            verb = tok
            break
        if "=" in tok or tok.startswith(("[", "!")):
            break
        segs.append(tok)
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


def predict_label(task: dict, candidate_cmds: list[str]) -> tuple[str, dict]:
    cand = candidate_cmds[0] if candidate_cmds else ""
    # unsafe: matches a forbidden command
    for fb in task.get("forbidden_commands", []) or []:
        if cand.strip() == fb.strip():
            return "unsafe", {"reason": "matches forbidden_command"}

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

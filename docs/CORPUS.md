# Task Corpus — what the benchmark actually tests

The benchmark is driven by a single task corpus, [`tasks/corpus.yaml`](../tasks/corpus.yaml):
**49 RouterOS v7 tasks**, each a natural-language intent plus the device-true
"gold" command(s) and metadata (target menu areas, safety class, state
dependency, version scope, optional decoys/forbidden commands).

Two consumers read it:

- **Structural metrics** (model-free) run over **all 49** — token cost, tool-selection
  ambiguity, retrieval coverage, command-syntax validity, the deterministic scorer.
- **The live ladder** (`harness/live/run_live_ladder.py`) sends a balanced
  **11-task subset** through real `claude -p` generations, scored by the same
  scorer and CHR `/console/inspect` validator. See
  [`REPORT_LIVE.md`](REPORT_LIVE.md).

> Scope is RouterOS **v7** (validated on CHR 7.22.1 / 7.23.1). The corpus
> intentionally mixes "everyone should get this" baseline config with a small set
> of **config traps** that discriminate the augmentation strategies.

## Kinds of test

A task sits on several orthogonal axes. Together they decide _what_ a given task
probes about an agent.

| Axis | Values (count) | What it probes |
|---|---|---|
| **Operation** | write-config (41), read-only (7), destructive (1) | safe-by-default behavior; whether a destructive intent is flagged |
| **State dependency** | stateless (14), mutation (17), needs-config (11), read-only (7) | can the command stand alone, or does it need prior config / a `[find]` selector |
| **Command shape** | `add` create · `set [find …]` selector-mutate · `disable`/`enable [find]` · `print`/`export` read · multi-step sequence | idiom fluency (e.g. idempotent `[find]` selectors, ordered rule insertion) |
| **Version scope** | stable-v7 (45), 7.21+ (3 = WireGuard), 7.22+ (1 = `/interface/wifi`) | version-aware menus/properties, not v6 priors |
| **Trap?** | straightforward (43), **config trap** (6) | whether a plausible training prior yields a _device-wrong_ form a technique can be seen to fix (or not) |

The first four are "does the agent know routine RouterOS?" The fifth — the trap
set — is where the benchmark earns its signal: most non-trap tasks are
"everyone perfect," so technique deltas concentrate on the traps.

## The config-trap taxonomy (the discriminating tasks)

A _config trap_ is a task where the common, plausible answer (usually a v6 or
cross-vendor prior) is **rejected by the device**, so a grounding technique can be
measured fixing it — or failing to. Each trap populates a different cell of the
taxonomy.

| task | trap class | plausible-but-wrong prior | device-true v7 form | how it's caught |
|---|---|---|---|---|
| `route-blackhole` | v6-deprecated `type=` / flag-shape | `type=blackhole`, or `blackhole=yes` | bare flag `… blackhole` | scorer `hallucinated` + **CHR rejects**; gold device-verified ([`data/blackhole_device_verify.csv`](../data/blackhole_device_verify.csv)) |
| `route-unreachable` | **removed capability** | `type=unreachable` (also `unreachable=yes`, bare `unreachable`, `prohibit`) | **none exists** — no v7 form creates it; closest is `blackhole` | `trap-fell` / `trap-avoided`; device-verified ([`data/route_unreachable_device_verify.csv`](../data/route_unreachable_device_verify.csv)) |
| `dhcp-server-on-bridge` | valid-syntax / dead-semantics (silent default) | omit `disabled=no` (server defaults `disabled=yes`) | `… disabled=no` | scorer `missing_arg`; **syntax-valid but functionally dead** — no validator catches it |
| `ipaddr-netmask-form` | cross-vendor | `netmask=255.255.255.0` (Cisco/Linux habit) | CIDR `address=192.168.50.1/24` | scorer `hallucinated` + CHR rejects unknown `netmask` |
| `fw-filter-comment-not-name` | menu-specific arg | `name=allow-est` (filter rules have no `name`) | `comment=allow-est` | scorer `hallucinated` + CHR rejects unknown `name` |
| `ipv6-address-assign` | v7 menu reorg | `/ip/address add … (a v6 address)` | `/ipv6/address add …` | scorer `wrong_path` |

Two of these are the spine of the live findings:

- **`route-blackhole` — a _form-change_ trap.** The capability survives but the
  syntax moved (v6 `type=blackhole` → v7 bare `blackhole` flag). Grounding _can_
  fix it because there is a correct form to retrieve. It also exposed the
  **inspect-vs-runtime gap**: `/console/inspect` _accepts_ the device-rejected
  `blackhole=yes`, so only real execution catches it. (REPORT_LIVE Finding 1.)
- **`route-unreachable` — a _removed-capability_ trap.** The v6 `unreachable` /
  `prohibit` route types have **no creatable v7 form at all** — `/ip/route add`
  exposes only 13 args and `blackhole` is the lone discard flag. Because the
  capability was _deleted, not renamed_, retrieval has nothing correct to surface,
  so even rosetta falls for it like baseline. Only a device run tier catches it.
  (REPORT_LIVE Finding 7.)

## The live-ladder subset (11 tasks sent through models)

Balanced to stress different failure modes: routine single-line config, a
multi-step sequence, arg-completeness, "weird syntax," and the six traps above.

| task | intent | gold / v7-true form |
|---|---|---|
| `vlan-create-basic` | Create VLAN 100 named vlan100 on ether2 | `/interface/vlan add name=vlan100 vlan-id=100 interface=ether2` |
| `vlan-bridge-untagged-pvid` | Access VLAN 30 on ether4 (untagged + pvid) | `…/bridge/vlan add … untagged=ether4 vlan-ids=30` **+** `…/bridge/port set [find interface=ether4] pvid=30` |
| `nat-dstnat-port-forward` | Forward ext tcp/8080 → 192.168.88.20:80 | `/ip/firewall/nat add chain=dstnat protocol=tcp dst-port=8080 action=dst-nat to-addresses=… to-ports=80` |
| `fw-allow-established-related` | Input rule accepting established,related | `/ip/firewall/filter add chain=input connection-state=established,related action=accept` |
| `wg-add-peer` | WireGuard peer on wg0 (allowed-address + pubkey) | `/interface/wireguard/peers add interface=wg0 public-key="…" allowed-address=10.10.0.2/32` |
| `route-blackhole` | Blackhole 10.10.10.0/24 | `/ip/route add dst-address=10.10.10.0/24 blackhole` _(trap)_ |
| `route-unreachable` | Unreachable route for 172.16.0.0/12 | _no satisfiable gold; v7-closest is `… blackhole`_ _(removed-capability trap)_ |
| `dhcp-server-on-bridge` | DHCP server dhcp1 on bridge1 using a pool | `/ip/dhcp-server add name=dhcp1 interface=bridge1 address-pool=dhcp_pool0 disabled=no` _(trap)_ |
| `ipaddr-netmask-form` | Assign 192.168.50.1 mask 255.255.255.0 to bridge1 | `/ip/address add address=192.168.50.1/24 interface=bridge1` _(trap)_ |
| `fw-filter-comment-not-name` | Accept established,related, labelled allow-est | `… add chain=input connection-state=established,related action=accept comment=allow-est` _(trap)_ |
| `ipv6-address-assign` | Assign 2001:db8:0:1::1/64 to bridge1 | `/ipv6/address add address=2001:db8:0:1::1/64 interface=bridge1` _(trap)_ |

The four conditions each task is run under — `baseline`, `rosetta-context`,
`skills-context`, and the agentic `vendordoc-steer` (steer the agent to read
`manual.mikrotik.com`) — are described in
[`LIVE_AGENT_HARNESS.md`](LIVE_AGENT_HARNESS.md).

## Full corpus reference (all 49, by domain)

`tags` legend: **live** = in the live-ladder subset · **trap** = config trap ·
**read** = read-only · **destructive** = destructive safety class · _N_-step =
multi-command gold · a version (`7.21+`, `7.22+`) = version-scoped.
<!-- BEGIN GENERATED: harness reads tasks/corpus.yaml; regenerate if the corpus changes -->

### vlan

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `vlan-create-basic` | Create VLAN 100 named vlan100 on ether2. | `/interface/vlan add name=vlan100 vlan-id=100 interface=ether2` | live |
| `vlan-on-vlan-qinq` | Create a service-tagged (QinQ) VLAN 200 named svlan on ether2. | `/interface/vlan add name=svlan vlan-id=200 interface=ether2 use-service-tag=yes` | — |

### bridge-vlan

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `vlan-bridge-tagged` | On bridge1, tag VLAN 20 on ether3 (egress tagged). | `/interface/bridge/vlan add bridge=bridge1 tagged=ether3 vlan-ids=20` | — |
| `vlan-bridge-untagged-pvid` | Set access VLAN 30 on ether4: untagged member and pvid 30. | `/interface/bridge/vlan add bridge=bridge1 untagged=ether4 vlan-ids=30` | live, 2-step |
| `vlan-enable-bridge-vlan-filtering` | Turn on VLAN filtering on bridge1. | `/interface/bridge set [find name=bridge1] vlan-filtering=yes` | — |

### ip-address

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `ipaddr-assign` | Assign 192.168.88.1/24 to bridge1. | `/ip/address add address=192.168.88.1/24 interface=bridge1` | — |
| `read-ip-addresses` | Show the configured IP addresses. | `/ip/address/print` | read |
| `ipaddr-netmask-form` | Assign 192.168.50.1 with subnet mask 255.255.255.0 to bridge1. | `/ip/address add address=192.168.50.1/24 interface=bridge1` | live, **trap** |

### ipv6

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `ipv6-address-assign` | Assign 2001:db8:0:1::1/64 to bridge1. | `/ipv6/address add address=2001:db8:0:1::1/64 interface=bridge1` | live, **trap** |

### interfaces

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `iface-create-bridge` | Create a bridge named bridge1. | `/interface/bridge add name=bridge1` | — |
| `iface-add-bridge-port` | Add ether2 as a port of bridge1. | `/interface/bridge/port add bridge=bridge1 interface=ether2` | — |
| `iface-disable` | Disable interface ether5. | `/interface/disable [find name=ether5]` | — |
| `iface-set-mtu` | Set the MTU of ether1 to 9000. | `/interface/ethernet set [find name=ether1] mtu=9000` | — |
| `read-interfaces` | List all interfaces on the device. | `/interface/print` | read |

### wireless

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `wifi-set-ssid` | On a wifi-capable device, set the SSID of wifi1 to MyNet. | `/interface/wifi set [find name=wifi1] ssid=MyNet` | 7.22+ |

### routes

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `route-default-gateway` | Add a default route via 192.168.1.1. | `/ip/route add dst-address=0.0.0.0/0 gateway=192.168.1.1` | — |
| `route-static-with-distance` | Add a backup default route via 192.168.2.1 with distance 2. | `/ip/route add dst-address=0.0.0.0/0 gateway=192.168.2.1 distance=2` | — |
| `route-blackhole` | Blackhole the 10.10.10.0/24 network. | `/ip/route add dst-address=10.10.10.0/24 blackhole` | live, **trap** |
| `read-routes` | Show the routing table. | `/ip/route/print` | read |
| `route-unreachable` | Add an unreachable route for 172.16.0.0/12. | `/ip/route add dst-address=172.16.0.0/12 blackhole` | live, **trap** |

### firewall

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `fw-allow-established-related` | Add an input rule accepting established and related connections. | `/ip/firewall/filter add chain=input connection-state=established,related action=accept` | live |
| `fw-drop-invalid` | Drop invalid connections on the input chain. | `/ip/firewall/filter add chain=input connection-state=invalid action=drop` | — |
| `fw-allow-wireguard-peer` | Allow inbound WireGuard on udp/13231 to the router. | `/ip/firewall/filter add chain=input protocol=udp dst-port=13231 action=accept` | — |
| `fw-block-port-forward-order` | Add a forward rule (placed first) accepting tcp/443 to 192.168.88.10. | `/ip/firewall/filter add chain=forward protocol=tcp dst-address=192.168.88.10 dst-port=443 action=accept place-before=0` | — |
| `fw-addresslist-add` | Add 10.0.0.0/8 to an address list named rfc1918. | `/ip/firewall/address-list add list=rfc1918 address=10.0.0.0/8` | — |
| `read-firewall-filter` | List the firewall filter rules in order. | `/ip/firewall/filter/print` | read |
| `fw-default-drop-input-last` | Add a final input rule dropping everything (a default-drop, placed last). | `/ip/firewall/filter add chain=input action=drop` | **destructive** |
| `mangle-mark-connection` | Mark connections from 192.168.88.0/24 with connection-mark lan-conn in prerouting. | `/ip/firewall/mangle add chain=prerouting src-address=192.168.88.0/24 action=mark-connection new-connection-mark=lan-conn` | — |
| `fw-filter-comment-not-name` | Add an input rule accepting established,related and label it allow-est. | `/ip/firewall/filter add chain=input connection-state=established,related action=accept comment=allow-est` | live, **trap** |

### nat

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `nat-masquerade-out` | Masquerade traffic leaving ether1. | `/ip/firewall/nat add chain=srcnat out-interface=ether1 action=masquerade` | — |
| `nat-dstnat-port-forward` | Port-forward external tcp/8080 to 192.168.88.20:80. | `/ip/firewall/nat add chain=dstnat protocol=tcp dst-port=8080 action=dst-nat to-addresses=192.168.88.20 to-ports=80` | live |

### dhcp

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `dhcp-server-pool` | Create a DHCP pool dhcp_pool0 covering 192.168.88.10-192.168.88.254. | `/ip/pool add name=dhcp_pool0 ranges=192.168.88.10-192.168.88.254` | — |
| `dhcp-server-on-bridge` | Create a DHCP server named dhcp1 on bridge1 using pool dhcp_pool0. | `/ip/dhcp-server add name=dhcp1 interface=bridge1 address-pool=dhcp_pool0 disabled=no` | live, **trap** |
| `dhcp-network-gateway-dns` | Add a DHCP network 192.168.88.0/24 with gateway 192.168.88.1 and DNS 1.1.1.1. | `/ip/dhcp-server/network add address=192.168.88.0/24 gateway=192.168.88.1 dns-server=1.1.1.1` | — |
| `dhcp-static-lease` | Make a static DHCP lease binding 192.168.88.50 to MAC AA:BB:CC:DD:EE:FF. | `/ip/dhcp-server/lease add address=192.168.88.50 mac-address=AA:BB:CC:DD:EE:FF` | — |
| `read-dhcp-leases` | Show current DHCP leases. | `/ip/dhcp-server/lease/print` | read |

### dns

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `dns-set-servers` | Set the router DNS servers to 1.1.1.1 and 8.8.8.8 and allow remote requests. | `/ip/dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=yes` | — |
| `dns-static-record` | Add a static DNS A record router.lan -> 192.168.88.1. | `/ip/dns/static add name=router.lan address=192.168.88.1` | — |

### wireguard

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `wg-create-interface` | Create a WireGuard interface wg0 listening on udp/13231. | `/interface/wireguard add name=wg0 listen-port=13231` | 7.21+ |
| `wg-assign-address` | Give wg0 the address 10.10.0.1/24. | `/ip/address add address=10.10.0.1/24 interface=wg0` | 7.21+ |
| `wg-add-peer` | Add a WireGuard peer on wg0 with allowed-address 10.10.0.2/32 and a given public key. | `/interface/wireguard/peers add interface=wg0 public-key="REPLACE_PUBKEY=" allowed-address=10.10.0.2/32` | live, 7.21+ |

### queue

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `queue-simple-limit` | Limit 192.168.88.50 to 10M/10M with a simple queue. | `/queue/simple add name=limit-host target=192.168.88.50/32 max-limit=10M/10M` | — |

### users

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `user-add-readonly` | Add a read-only user named auditor with a password. | `/user add name=auditor group=read password="REPLACE_PW"` | — |
| `user-disable` | Disable the user named olduser. | `/user disable [find name=olduser]` | — |

### system

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `identity-set` | Set the router identity (hostname) to core-router. | `/system/identity set name=core-router` | — |
| `ntp-client-enable` | Enable the NTP client pointing at pool.ntp.org. | `/system/ntp/client set enabled=yes servers=pool.ntp.org` | — |

### backup

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `backup-create` | Create a system backup named pre-change. | `/system/backup/save name=pre-change` | — |
| `export-config` | Export the full configuration to a file named full-config. | `/export file=full-config` | read |

### logs

| task | intent | gold (or v7-true form) | tags |
|---|---|---|---|
| `logs-read-recent` | Show recent system log entries. | `/log/print` | read |
<!-- END GENERATED -->

## Task schema

Each corpus entry carries:

| field | meaning |
|---|---|
| `id`, `domain`, `intent` | identifier, subsystem, the natural-language ask given to the agent |
| `gold_commands` | device-true command(s); empty for a `removed_capability` task |
| `acceptable_variants` | alternate forms scored as correct (e.g. selector vs property form) |
| `relevant_areas` | menu paths / keywords used by the retrieval + routing-signal metrics |
| `version` | `stable-v7`, `7.21+`, `7.22+` — version scope of the feature |
| `state_dependency` | `stateless` / `mutation` / `needs-config` / `read-only` |
| `safety_class` | `read-only` / `writes-config` / `destructive` |
| `removed_capability`, `trap_tokens` | mark a removed-capability trap and the v6 tokens that count as falling for it |
| `forbidden_commands` | (optional) forms scored as `unsafe` if emitted |

## Scoring labels

The deterministic scorer ([`lib/scorer.py`](../lib/scorer.py)) collapses a
candidate into one label:

| label | meaning |
|---|---|
| `perfect` | matches a gold / acceptable variant |
| `wrong_path` | right idea, wrong menu path (e.g. `/ip/address` for IPv6) |
| `hallucinated` | invented an arg/flag the menu doesn't have (e.g. `netmask=`, `name=` on a filter) |
| `missing_arg` | omitted a required arg (e.g. `disabled=no` on a DHCP server) |
| `wrong_target` | right shape, wrong identity value (address/name/id) |
| `incomplete_seq` | fewer commands than a multi-step gold requires |
| `unsafe` | matches a task's `forbidden_commands` |
| `empty` | produced no parseable command |
| `trap-fell` / `trap-avoided` | _removed-capability tasks only_ — emitted a removed v6 form, vs emitted the v7 alternative or recognized the removal |
| `session-limited` | the `claude -p` usage cap was hit; excluded from scoring, not counted as a model answer |

Live runs additionally CHR-validate each emitted command (`syntax_valid` =
`ok`/`error`/`n/a`), which is what surfaces the inspect-vs-runtime gap that a
label alone cannot.

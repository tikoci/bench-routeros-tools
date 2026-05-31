---
description: "Use when editing RouterOS command corpus, command validation, CHR integration, rosetta context, or RouterOS-facing prompts."
applyTo: "tasks/**/*.yaml,harness/validate_commands.py,lib/chr.py,lib/rosetta_client.py,lib/context_builders.py,fixtures/**/*.yaml,docs/**/*.md"
---

# RouterOS grounding

Ground RouterOS facts in inspect data, rosetta, or related tikoci projects before
changing corpus commands, validators, or prompt context.

- Prefer rosetta and the RouterOS skills for command paths, properties,
  versioning, and CLI syntax before general web search.
- Use CHR plus `/console/inspect` as the strongest syntax signal when QEMU and
  `CHR_IMG` are available; keep the rosetta static fallback working.
- For QEMU/CHR behavior, cross-check `quickchr` and the `routeros-qemu-chr`
  skill instead of re-learning boot, networking, and acceleration rules here.
- For future validate-then-run behavior, compare against `rosetta` for
  docs/schema, `centrs` for the runner direction, and `m2ir` for binary or
  saved-device-data boundaries.
- Keep RouterOS examples synthetic unless they are generated from a disposable
  CHR fixture.
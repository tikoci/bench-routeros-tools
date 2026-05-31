---
description: "Use when creating or editing Copilot/agent customization files in this repo, including AGENTS.md and .github/instructions files."
applyTo: "AGENTS.md,**/AGENTS.md,.github/instructions/**,.github/copilot-instructions.md"
---

# Instruction scopes

Keep root instructions pointer-oriented and move durable path-specific rules into
`.github/instructions/*.instructions.md`.

- Use the narrowest `applyTo` patterns that cover the files governed by the
  instruction.
- Prefer one canonical source per rule; when a broad file overlaps a narrower
  file, keep the narrower file normative and make the broad file a pointer.
- Link existing docs such as `README.md`, `REPORT.md`,
  `docs/LIVE_AGENT_HARNESS.md`, and `data/PROVENANCE.md` instead of copying
  their content.
- Give every instruction a keyword-rich `description` so it can be discovered
  on demand.
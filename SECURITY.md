# Security Policy

## Reporting a Vulnerability

Report privately via [GitHub Security Advisories](https://github.com/tikoci/bench-routeros-tools/security/advisories/new). Do **not** open a public issue for an undisclosed vulnerability.

Please include the affected files or workflow, reproduction details, and impact. Initial response within a few business days; fixes land on `main` and flow into the next published artifact.

## Scope

This project is a benchmark harness. It can launch a local RouterOS CHR VM in
QEMU, query rosetta over MCP stdio, inspect local skill markdown, and optionally
refresh tool-schema snapshots from external checkouts. It should not connect to
production routers or store live credentials; fixtures and results must remain
synthetic or sanitized.

## Code scanning

The repository's [Security tab](https://github.com/tikoci/bench-routeros-tools/security) is the live source of current alerts and advisories. This section describes *what* checks run and *why*, so the doc stays meaningful even when the badge is at 0.

- **CodeQL** — repo-managed workflow at [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) with config [`.github/codeql/codeql-config.yml`](.github/codeql/codeql-config.yml). Query suite: `security-and-quality` (security-extended + code-quality). Languages: Python, Actions. Schedule: push to `main`, pull requests to `main`, weekly cron.
- **Code Quality (AI findings, preview)** — not enabled at repository creation time. If enabled later, AI findings are noisy and self-contradicting; we accept the noise because the second-opinion catches real issues that the static suite misses. Steady-state goal is 0 open findings. False positives are dismissed via the GitHub UI with a written justification.
- **Dependency review** — [`.github/workflows/dependency-review.yml`](.github/workflows/dependency-review.yml), `fail-on-severity: high` on pull requests.
- **Dependabot security updates** — not enabled at repository creation time.
- **Secret scanning** — not enabled at repository creation time.
- **Private vulnerability reporting** — not enabled at repository creation time.

## Supported versions

| Version | Supported |
| --- | --- |
| `main` | Yes |
| older snapshots | No |

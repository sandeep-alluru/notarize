# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `compare_traces()` and `TraceComparison` / `StepComparison` for step-by-step trace diffing
- `timeline.py`: `to_csv()`, `to_timeline_json()`, `to_compliance_report()` export formats
- `audit.py`: `AuditSummary`, `summarize()`, `summarize_session()` for compliance risk scoring
- CLI `notarize audit <file>` command with rich and JSON output modes

## [0.1.0] - 2026-06-18

### Added
- `TraceStep` content-addressed dataclass: SHA-256[:16] of step_index|action|observation|result
- `AgentTrace` hash-chained trace: each step's parent_id links to the previous step's ID
- Merkle root over sorted step IDs — tamper any step and the root breaks
- `ConsistencyVerifier` with 5 checks: hash chain, Merkle root, monotonic indices, no duplicates, trace ID
- `PrivacyScrubber` for structure-preserving PII redaction (email, phone, credit card, SSN, IP)
- `TraceStore` — SQLite-backed persistence for traces and verification results
- Rich terminal output, JSON, and Markdown formatters
- Click CLI: `verify`, `scrub`, `log`, `status` subcommands
- FastAPI REST server: `/health`, `/verify`, `/scrub`, `/traces`, `/trace/{id}`
- MCP server (`notarize-mcp`) for native Claude tool integration
- 123 unit tests, 88.6% branch coverage

[Unreleased]: https://github.com/sandeep-alluru/notarize/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeep-alluru/notarize/releases/tag/v0.1.0

# Competency Evidence
Implementation evidence as of 2026-10-06: Greenhouse/Ashby ingestion, PostgreSQL
UPSERT and conservative location normalization in the separate implementation
repository. [Sprint 3 validation](../contexto/Handover/sprint_3_handover.md)
records 59 passing tests, migration reversal, concurrency and real CLI reruns.
This is project evidence, not a claim of professional experience or measured ROI.

| Competency | Intended artifact | Verification | Current status |
|---|---|---|---|
| Data extraction | Ashby/Greenhouse adapters | Ashby contract tests and real CLI reruns | Verified for these boards; retries not implemented |
| Data engineering | PostgreSQL UPSERT and migrations | Concurrent writes and reversible schema migration | Verified subset; history and clean-clone reproduction pending |
| Analytics engineering | SQL/dbt models | Grain, keys, relationships and metric reconciliation | Not implemented |
| Data visualization | Decision-focused report | Metrics reconciled to source models | Not implemented |
| Data quality | pytest suite | 59 tests passed including two PostgreSQL integration tests | Verified scope; broad geography coverage not claimed |
| Technical communication | README and architecture rationale | Technical walkthrough by the author | Initial documentation; walkthrough not assessed |

For each completed increment, replace intentions with links to actual artifacts, the procedure performed, observed results and limitations. Keep candidate records and private learning assessments outside the public repository.

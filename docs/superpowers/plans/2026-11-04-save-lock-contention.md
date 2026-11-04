# Fix public field saves blocked by background deployment

User requested diagnosis and repair. Execute inline with TDD, preserving all knowledge and deployment/lease safety.

## Root cause

Public formal saves use fail-fast sync_lock. retry_canonical holds the same lock while running full sync-check (measured tens of seconds in earlier deployments). Release remote probes and bulk image backups also run under this lock. Thus ordinary saves fail with the raw English SyncBusy error during periodic background work.

## Implementation

- [x] Add regression tests for a field save during brief contention, saving another note during validation, and unlocked deployment network/image-copy stages.
- [x] Under the short sync lock, recover durable journals/approval receipts, commit captured formal changes, and capture the immutable Git head. Validate only the isolated candidate outside the save lock; retain candidate validation before push and dirty/head checks so later saves remain queued.
- [x] Move release ls-remote probes and immutable published-image copies outside the save lock. Keep mutable backup snapshots and final activation checks protected; retain stale-release refusal and rollback.
- [x] Give HTTP formal saves/approvals/resolutions a bounded three-second lock wait. Preserve revisions, request IDs, leases and drafts; return a Chinese save_busy error if still busy.
- [ ] Run relevant Python and frontend regressions/build; fresh read-only review, publish through existing workflow and verify target server commit. Exercise the published Python HTTP save path on Linux with disposable data, without altering real notes.

## Constraints

Do not delete locks, kill existing jobs, skip validation, force-push, or bypass revision/edit leases. Preserve local behavior and viewer permissions. Scope is save contention, not note content.

## Verification ledger

- RED reproduced the exact English SyncBusy failure during full validation, HTTP 423 for a 350ms lock, and deployment remote queries retaining the save lock. GREEN after fixes.
- Concurrent validation/save keeps the later edit queued and publishes it on the next retry. Durable manual journal recovery passed. Busy timeout returns save_busy without writing the attempted value.
- Full suites: 107 backend/save/sync tests OK (1 skipped), 35 deployment tests OK (1 skipped), 193 frontend tests passed; production build and git diff --check passed. Deployment ERROR logs are intentional rollback scenarios in temporary fixtures.
- Fresh read-only review found no important issues; candidate validation, stale activation protection, image snapshot consistency, roles, leases and idempotency retained.
- Next: publish and exercise the installed Linux code with disposable fixtures; retain logs under raw/local-sync/.

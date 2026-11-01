# Immediate approval feedback and background synchronization

Approved contract: public formal writes return only after canonical content and
approval results are durable, with additive sync status. Git is background work.
Pending sync blocks further formal writes, but private proposal CRUD stays usable.
Local edits never push. No real commits/pushes/server operations in this task.
Existing Pokilot branch-fix changes are unrelated and must be preserved.

## Tasks
- [x] 1. Fast equivalent website validation and one-process sync-check.
- [x] 2. Public read projection caching and proposal read/idempotency efficiency.
- [x] 3. Durable sync queue, lightweight status, fast Git path and managed processes.
- [x] 4. One public worker with recovery, retries, cancellation and release guards.
- [x] 5. HTTP save/enqueue split, proposal lock separation and admin retry endpoint.
- [x] 6. Frontend immediate feedback, progress, polling and retry.
- [x] 7. Regression suites, comparable102-note benchmark, browser smoke, final review.

## Decisions
- Keep the existing checkout and no Git mutations, per the user's explicit workflow
  and existing uncommitted work; do not create another checkout or copy note data.
- Public worker starts explicitly in the public entrypoint, not on create_server
  in tests. CLI/release retry remains synchronous and uses the same external lock.
- Durable sync.json owns job identity, actual release root, phase and retry time;
  startup reconciles canonical journals/approval receipts/dirty formal paths to
  cover a crash between canonical commit and queue persistence.
- Proposal non-formal mutations need only SQLite transactions unless recovering
  an interrupted approval. Only canonical changes and Git use the long sync lock.
- Network retry intervals30/60/120/300 seconds, then300 indefinitely. Conflicts
  require explicit administrator retry. Pending-deploy waits for publication.
- All new behavior is tested RED→GREEN; final review covers job-root fencing,
  response durability, duplicate requests, cancellation and cache privacy.

## Evidence / ledger
- Baseline profile:102 notes,53.072s instrumented validation,41.599s deepcopy.
  This is local profiling data, not measured production latency.
- Equivalent optimized profile:102 notes,10.283s (80.6% less), with package hash,
  structure, reference and semantic validation retained. Catalog calls0.314s
  cold and0.109/0.101s warm. No canonical records or real remotes were changed.
- Queue/fast-path/worker/HTTP/UI regressions were RED then GREEN. Full frontend
  Python156 ran:154 passed,2 POSIX-specific tests skipped on Windows. JS147 passed.
- Ruling: repeated Windows10053 errors in the existing early-rejection matrix
  were traced to closing sockets with unread small bodies. A delayed-body test
  reproduced the problem; bounded draining (64KiB/2s) on early refusal fixes it
  without changing accepted request bodies or public route authorization.
- Publication now waits up to300s for the external sync lock rather than failing
  immediately when a background job owns it; a real lock-holder regression passed.
- Managed worker subprocess cancellation, reaping, resumed save, root fencing,
  source-job retry protection, backoff and private CRUD during blocked Git passed.
- Chromium public fixture: approval-to-refresh851ms including an injected600ms
  response delay; actual Git remains blocked. Progress/pending write gate, failure
  feedback and manual retry succeeded without rendering errors. Screenshots/logs
  are ignored temp artifacts. Production/local builds passed (chunk advisory only).
- Independent final review found four P2 issues, all addressed in one fix pass:
  cleanup errors across the save/enqueue boundary now persist/wake recovery;
  private mutations skip unguarded internal recovery and check receipt presence
  after BEGIN IMMEDIATE; direct CLI/release retry rejects foreign source jobs;
  role mutation completion invalidates in-flight old-cookie polls. Each was
  reproduced RED and verified GREEN, including a delayed real-browser poll race.
- Final evidence: frontend Python159 ran (157 passed,2 POSIX cases skipped),
  JavaScript147 passed, deploy63 ran (62 passed,1 Linux-root case skipped).
  Release10 passed again after the ownership fix. Browser final approval refresh
  854ms including600ms injected delay, phase text readable, failure/manual retry
  and delayed-poll role isolation passed. Both build bases passed; compilation and
  git diff --check passed. No production actions or real commits/pushes were run.

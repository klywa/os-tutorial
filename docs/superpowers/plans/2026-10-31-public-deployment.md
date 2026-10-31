# Public Deployment Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; independent Pokilot and UI work may use superpowers:dispatching-parallel-agents.

**Goal:** Deliver dual subpath deployment, public read-only mode with admin editing, hourly Git sync, and executable deployment instructions.
**Architecture:** Existing React/Vite + Python app gains a separate public request handler without crawler initialization. A tracked sanitized dataset supplies offline reads. Serialized Git edits and staged releases preserve pending edits and last successful versions. Pokilot uses configurable Next basePath.
**Tech Stack:** Python 3.12 stdlib, React, Vite, Next.js, Git, Caddy, systemd.
**Spec:** ../specs/2026-10-31-public-deployment-design.md

## Global Constraints
- Preserve existing uncommitted changes. No development commits, pushes, branches or live deployment.
- Public /os-tutorial, Pokilot /pokilot, local defaults unchanged.
- No public crawling, transcription, official refresh, raw/source data or local credentials.
- Configuration outside Git; admin klywa / aa2025, 168-hour cookie.

## Review Focus
- Anonymous/direct routes must not bypass UI restrictions; test all HTTP methods.
- Public startup must not instantiate crawler or mutate knowledge; test startup with runtime mocked to fail.
- Concurrent Git changes and network errors must retain admin edits; use temporary remotes.
- Prefixes must cover API, raw images/links, auth, refresh and bookmarks in both apps.
- Dataset export and release switch must not silently overwrite matching or pending edits.

## Tasks
- [x] 1. Public Python handler/auth: HTTP authorization, signed sessions, origin checks, no workers, prefix routing verified.
- [x] 2. Dataset export: sanitized package exported; 102 canonical notes validate, 952 cards and 1714 images; matching preserved.
- [x] 3. Git synchronization/deployment: temporary-remote sync and staged release/rollback tests pass, templates provided.
- [x] 4. React public capabilities: auth, readonly notes, admin matching and base paths; 133 tests and build pass.
- [x] 5. Pokilot basePath: 2700 tests pass (1 skipped), typecheck/build/production browser probe pass; legacy root-cookie regression covered.
- [x] 6. docs/depolyment.md + READMEs: complete Windows/Ubuntu commands, backups/keys/config/services/Caddy/acceptance/recovery/rollback.
- [x] 7. Whole change verification/review: 90 frontend Python + 7 release tests pass; 531 knowledge tests pass with unrelated background usage tick mocked; independent offline HTTP smoke reads all 102 notes and four scopes without network.

## Execution ledger
- User approved full plan and requested continued execution. Existing current checkouts retained to include uncommitted project behavior; no auto commits. Independent agents edit disjoint frontend/Pokilot files while primary owns backend/data/sync/docs.
- Review fixed: interrupted save journal must replay before Git change selection; RED→GREEN ordering + startup tests. Validation rejects unresolved overlay rather than claiming disk is coherent.
- Review fixed: proxy login rate limit uses trusted loopback Caddy's rightmost X-Forwarded-For; RED→GREEN independent visitor test.
- Regression fixed: clean releases can start under held publisher lock; only an interrupted release acquires recovery lock. RED→GREEN startup test.
- Ruling: normal live code is never merged in place. Successful temporary merge freezes editing until next hourly release (pending-deploy); this may delay further edits by an hour, and preserves complete schema/code releases.
- Full knowledge suite initially entered an unrelated real usage scraper in crawler cleanup. Stopped only the identified test processes; reran all 531 tests with UsageWorker.tick mocked (usage scheduling separately covered by frontend tests).
- Actual Linux symlink/systemd/Caddy/SSH/HTTPS deployment is left to documented server acceptance; no credentials configured or remote Git mutated by development.

# Reader startup and global task state implementation plan

> Execute inline with executing-plans and TDD. User approved implementation and publication on 2026-11-04.

**Goal:** Reduce public first-note startup median by at least 40% and keep global tasks folded by default, preserving the user's choice across note changes.

**Architecture:** Keep authorization before mounting content and memory-only public knowledge caches. Cache only content-hashed static assets long-term. Load card enhancement after the first note DOM; coalesce concurrent card catalog reads within a request generation/workspace. Keep activity expansion in stable App state.

## Constraints

- Preserve note bodies, metadata, JSON export, viewer permissions, logout/expiry cleanup and local anonymous access.
- JS/CSS under dist/assets with Vite content hashes get public, max-age=31536000, immutable. HTML stays no-cache; protected API and images retain private/no-store behavior.
- Caddy encode zstd gzip applies only to /os-tutorial/*; back up, validate and gracefully reload the live configuration. Keep other routes untouched.
- Refresh starts folded. Explicit expansion/collapse survives note navigation and activity refresh, without localStorage persistence.

## Tasks

- [x] Sync verified latest master c14e816 and restore local 8766 service.
- [x] Add RED tests for controlled task expansion, concurrent cards and static cache policy; implement minimal changes and verify GREEN.
- [x] Gate CardProvider on first-note readiness outside keyed per-note provider; keep already activated card loading alive across navigation. Browser-test delayed cards, two notes, active tasks and mobile/desktop.
- [x] Run frontend/Python regressions and production build; fresh read-only review and fix material findings.
- [ ] Publish through existing script, await Actions and verify server commit/service/timer. Apply backed-up and validated Caddy compression. Compare three authenticated reloads under the same browser/network setup and verify >=40% median improvement.

## Interfaces

- loadCardCatalog(workspace = activeWorkspace()): Promise<CardSummary[]>; shares only in-flight reads, keyed by requestGeneration and workspace. Clears on settle/reset; failures remain retryable.
- CardProvider enabled?: boolean; defaults true, latches activation for the mounted session. App enables after a note is rendered or a standalone non-note view is ready.
- GlobalActivity expanded: boolean, onExpandedChange(value: boolean): void; App owns initial false state.

## Progress ledger

- Baseline diagnosis: authenticated reloads 6.3–9.6s, JS 683KB, cards 764KB, no Caddy encoder and duplicate card reads; server note reads 9–15ms. Same-condition three-reload baseline being recorded in raw/local-sync/reader-performance-baseline.json.
- Sync transport intermittently failed TLS. Ruling: verify remote master via ls-remote and reuse the already fetched exact commit for redundant fetches inside the existing LocalSync flow; retain all validation, lock, activation and service restoration steps. Completed clean fast-forward to c14e816.
- RED tests reproduced ignored controlled expansion, missing shared catalog loader and no immutable asset policy; GREEN after implementation. Final frontend suite: 51 files / 193 tests passed. Python auth/cache/role suite: 59 tests passed (3 skipped). Production build passed; git diff --check clean. Fresh read-only review: no important findings.
- Mobile and desktop browser acceptance passed: delayed cards do not block note DOM, entities enhance after cards arrive, navigation reuses catalog, active tasks initially folded, manual state persists across notes/polling, reload folds again. Artifacts: temp/reader-startup-browser/.
- Three-run same-condition baseline median: visible 3098ms, first note DOM 2979ms; target visible <=1859ms. Raw record: raw/local-sync/reader-performance-baseline.json.
- Live Caddy handler now has encode zstd gzip; validated and gracefully reloaded. Backup: /etc/caddy/Caddyfile.backup-wxq-compression-20261104T075615Z. Verified gzip response on JS; unrelated handlers untouched. Details: raw/local-sync/reader-compression-20261104.log.

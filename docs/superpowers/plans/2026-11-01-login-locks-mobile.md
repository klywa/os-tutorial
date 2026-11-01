# Login modal, entry leases and mobile continuous reading

> Implement inline with superpowers:executing-plans and test-driven-development;
> one independent final review after integration.

Goal: top-right modal login, real per-entry mutual exclusion with administrator
takeover, and a full-width mobile reader with a left drawer and chapter anchors.
Stack: existing Python/SQLite/React/TypeScript, no new services or dependencies.
Spec: approved design in this conversation (2026-11-01).

## Constraints and decisions
- No actual commit/push/deployment; preserve accounts, proposal privacy and local
  no-auto-Git behavior. Existing checkout is reused as explicitly requested.
- Key+value is one unit. Chapter opening does not reserve every entry. Dirty
  entries remain leased until submit/cancel; unchanged blur releases.
- Admin takeover or approval clears only that annotator entry's unsubmitted
  draft. Other drafts/pending proposals remain. Admins do not clear each other.
- Leases use60s expiry,15s heartbeat,2s visible presence polling, owner+tab+token.
  Submitted proposals release leases. Private proposal edits share the body lock.
- Network/restart pauses preserve drafts; takeover clears affected drafts.
- SQLite lease/request tables share proposals.sqlite3; opaque tokens never in
  public presence. Delta submissions use captured baselines and request_id.
- Public legacy annotator writes without leases are denied. Admin whole-document
  saves retain revision checks and coordinate/revoke affected annotator fields.
- Mobile <=760px: left overlay drawer, click-outside/Escape/accepted navigation
  closes, internal search/filter stays open. Continuous current-note sections,
  tabs are anchors/scrollspy. Desktop reading mode remains unchanged.
- Existing palette:102438/18334D/72D5B5/E7BF76/E4EDF4/C47873, system Chinese font,
  mobile body16px/1.85 and primary touch controls44px.

## Tasks
- [x] 1. Lease store, epoch/revocation/request schema and unit regressions.
- [x] 2. Delta proposals, atomic lease checks, canonical receipts/admin guard.
- [x] 3. Public/local HTTP routes, permission/lifecycle and bypass tests.
- [x] 4. Client leases: inline entries, proposal edits, takeover and reconnect.
- [x] 5. Modal login/account menu, mobile drawer/continuous reader.
- [x] 6. Python/JS/build/browser multi-account/viewport verification and review.

## Review focus
No check/use gaps in lease validation; no inverted global/SQLite/workspace lock
order; lost HTTP responses don't duplicate inserts; stale clients cannot renew or
release a new owner's lease; unrelated edits don't get reverted by old chapter
snapshots; revoked drafts cannot reappear from stale fetches; guest/private cache
separation; browser navigation/login does not discard another entry's draft.

## Ledger
- Starting checkout clean; no Git mutations are authorized for this task.

- Lease protocol tests RED first (missing delta APIs), then GREEN: exclusive entry
  leases, distinct tabs/slots, explicit admin takeover, fencing, epochs, baseline
  validation, shared proposal edits, idempotence and durable canonical receipts.
- HTTP deltas replace legacy annotator chapter snapshots. Full admin edits retain
  revision checks and reserve/revoke only affected entries/positions.
- Independent final review found three important issues: uncertain-response retry,
  bare-worker receipt recovery, and a stale presence snapshot racing acquisition.
  Fixed with exact outstanding request replay (including pending Git status),
  recovery of exact lease IDs without epoch changes, and poll-start ownership IDs.
  Bare-store recovery tests reproduced both failures before the fix.
- Mobile top-of-document scrollspy regression reproduced in browser and fixed;
  desktop chapter selection behavior retained.
- Existing full Python suite: 176 tests, 2 platform skips; deployment: 63 tests,
  1 platform skip. Frontend: 150 tests pass. Production build passes (existing
  bundle-size advisory remains). Isolated Chromium captures six viewport sizes.
- User scope overrides skill integration menu: leave current checkout changes
  uncommitted; no merge, commit, push, worktree cleanup or server action.

- Final browser pass includes delayed pre-acquisition presence snapshots,
  lost-response replay after lease release, transient disconnect/reconnect,
  canonical/proposal lock sharing, targeted approval/direct takeover, and two
  administrator sessions rebasing without automatic draft loss. All passed.
- Screenshots and command logs: temp/login-locks-browser/,
  temp/login-locks-browser-final.log, temp/login-locks-build-final.log,
  temp/login-locks-python-final.log, temp/login-locks-deploy-final.log,
  temp/login-locks-js-final.log. Test-owned Chromium/localhost fixture stopped.

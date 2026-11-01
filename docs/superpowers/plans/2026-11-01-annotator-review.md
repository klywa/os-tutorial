# Annotator Review Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; disjoint implementation domains use superpowers:dispatching-parallel-agents.

**Goal:** Add one-command two-site updates, scoped entry insertion and private per-entry annotator review.
**Architecture:** Signed effective roles gate existing local/public handlers. Persistent proposals remain separate from canonical notes; approval uses recoverable receipts and the existing JSON edit pipeline. React mounts role-aware inline editing and private overlays. Linux updater wraps current release and isolated Pokilot rollback.
**Tech Stack:** Python stdlib/SQLite, React/TypeScript, Git/systemd.
**Spec:** ../specs/2026-11-01-annotator-review-design.md

## Global Constraints
- Preserve current docs/depolyment.md edits. No real deployment/commit/push/branch or credential changes.
- Public username klywa stays admin; initialize test1/aa2025 annotator without resetting existing credentials.
- No crawler activation or public source endpoints; no draft/proposal export or Git commits.
- Legacy config readable; v2 accounts makes old code fail closed. Local roles are loopback debug sessions and never auto push.

## Review Focus
- Account role caps effective role on every request, including local debug and forged cookies.
- Existing scoped replacement must include insert/delete without damaging outside nodes or semantics.
- Proposal author filtering must not leak through API caches or renderers.
- Crash between canonical journal/approval state cannot duplicate an insertion or lose a saved approval.
- Rollback must preserve proposal DB/WAL and original Pokilot DB, avoid holding a publisher lock across child publisher startup.

## Interfaces
- Session: mode, username, account_role, role, allowed_roles, base_path, optional sync. POST auth/role {role} returns Session and reissued cookie.
- Actor passed to proposals is {username,role,account_role}; authority uses role.
- ProposalStore(root,db_path): list(actor,note_id=None,status=None,author=None)->{items}; submit(actor,{note_id,revision,scope_id,nodes})->{items}; update(actor,id,{revision,proposed_node,rebase?})->item; action(actor,id,action,{revision})->item. actions approve/reject/withdraw; recover(); backup(path).
- Item fields: id,note_id,note_title,author,kind(insert/update/delete),node_id,section_id,after_id,base_node,proposed_node,revision(integer),status,created_at,updated_at,reviewed_by,result_revision; list may include conflict/current_node and insertion order fields.
- GET /api/proposals filters note_id/status/author; POST /api/proposals; PUT /api/proposals/ID; POST /api/proposals/ID/approve|reject|withdraw. Responses {items} for list/submit, item for update/action. Authorization failures403, guests401, stale409.
- HTTP owns external sync_lock for proposal writes and approvals; ProposalStore owns workspace edit lock via canonical edit pipeline. Public approve additionally checks sync state and record_save() after canonical apply; local never invokes Git.

## Tasks
- [x] 1. Root: auth v2 + signed role switching + local debug sessions + HTTP routing tests RED→GREEN; integrate ProposalStore and public/local write guards.
- [x] 2. Proposal worker: SQLite store, scoped diff validation, author access, rebase, partial review, recoverable canonical approval, WAL-safe backup; unit tests RED→GREEN.
- [x] 3. Frontend worker: session/capabilities/topbar, scoped insert/delete editor, private diff overlays and proposal drawer; meaningful tests + build.
- [x] 4. Updater worker: Linux update-sites + installer/config migration + safe two-site update/rollback + concise script-only docs; isolated tests.
- [x] 5. Root integration: HTTP permission/role/proposal persistence, full relevant Python/npm/build, fresh independent reviewer and regression fixes.

## Ledger
- User explicitly requested implementation. Existing checkout retained; only docs/depolyment.md dirty at start. Work divided by non-overlapping modules, no Git mutations.
- User steering: add publish-local.ps1/pull-local.ps1 with automatic Git and graceful local restart; replace deployment runbook with compact script-only instructions. New specification wording overrides preserving long prior runbook content.
- Auth tests4 RED→GREEN; public/local HTTP roles and private proposal partial approval validated. Full frontend Python127 passed before later stop/read regressions added.
- Browser smoke found missing server.py re import in local annotator GET; regression RED→GREEN added. Browser flow now passes role switch → chapter KV insert → private pending diff → admin per-item approval, no rendering errors.
- Final review fixed stale/canceled proposal rebase draft overwriting author's latest suggestion; pure payload regressions RED→GREEN. JS143 tests and local production build passed. Browser assertions additionally reproduce/fix topbar clipping and pending diff contrast.
- Updater review fixed with per-commit outgoing path validation, validated fixed Pokilot SHA, local build staging before checkout advancement, and configurable graceful stop wait. RED→GREEN regressions cover deleted secret history, remote advancement/database protection, failed build and activation runtime recovery, and slow confirmed shutdown. Installer/account migration and proposal WAL snapshots remain covered by isolated tests.
- Final static verification: project Python 3.12 compilation, PowerShell wrapper parsing, Bash installer syntax and git diff --check passed. Public /os-tutorial/ production build passed (existing chunk-size advisory only). Deployment guide now only shows script commands and minimal usage/status guidance.
- Final independent results: frontend Python128 passed with project Python3.12; knowledge531 passed; frontend JavaScript143 passed; deploy46 ran,45 passed and Linux-root ownership1 skipped on Windows. Default/public-prefix builds and isolated Chromium role/insertion/private-diff/approval flow passed. Logs/screenshots are ignored temp artifacts. One concurrent localhost origin-rejection request reset; isolated public12 and subsequent sequential full128 passed. An earlier unsupported system Python3.14 launch-test run was replaced by the supported-runtime verification.
- No real repository commit/push, production account migration, or server/service deployment was performed. Only temporary fixture repositories and mocked/isolated service tests were used. Server installation initializes test1; local default remains the per-browser debug administrator.

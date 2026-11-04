# Private reader and JSON export implementation plan

> Execute inline with superpowers:executing-plans. User approved this plan and publication on 2026-11-04.

**Goal:** Require known accounts on the public website, add read-only viewers and chapter-oriented JSON export, then publish and provision the three requested accounts.

**Architecture:** Extend existing Python signed sessions and React capabilities. Gate the application before mounting content. Public read caches are memory-only and scoped to an authenticated generation; local caching remains unchanged.

**Tech stack:** Python HTTP server, React, TypeScript, Vitest, existing PowerShell/GitHub Actions/SSH publishing.

## Constraints and decisions

- Reuse current checkout and preserve all existing edits; user explicitly approved publishing through the existing master-only publisher. Do not reset user work or create a divergent worktree.
- All existing authenticated roles may copy/export; viewer cannot edit, annotate, propose or acquire locks. Admin may simulate all three roles; annotator and viewer cannot elevate.
- Keep public login shell/assets and auth endpoints accessible; gate all content API routes before ETags. Local health check remains available.
- JSON is a reading artifact: schema_version 1, note id/title/type, sections with title/level/items/sections. Preserve Markdown values and repeated headings, use heading stack without invented levels, place leading content in an unnamed section. Legacy fallback uses reading sections/Markdown. No metadata or private sources.
- Public persisted cache is purged before content mounts; auth changes invalidate in-flight work. Local remains anonymous admin by default.
- Existing visual tokens: base #102438, panel #142c45, jade #72d5b5, gold #e7bf76, muted #a5b9c9; existing Chinese sans font stack. Restrained single-column login, left alignment, existing button styles. JSON button directly follows Markdown export.
- Passwords stay in server-only account configuration. New accounts: jojozhuo, willyang, sallensun, all viewer; use user-specified password without putting it in committed files. Never overwrite conflicting accounts.

## Tasks

- [x] 1. Add failing viewer/auth HTTP and role tests. Extend Auth, shared permissions, account scripts and public content guards; verify Python tests.
- [x] 2. Add failing tree export tests; implement noteJsonExport in a separate module and wire the button; verify Vitest.
- [x] 3. Add auth gate, request/session generation and memory-only public cache tests. Implement login screen, viewer hook guards and cache lifecycle; verify tests/build.
- [x] 4. Review complete change with a fresh read-only reviewer; fix actionable findings. Exercise login/export/expiry at mobile and desktop sizes.
- [ ] 5. Run existing publisher and await Actions; provision accounts with backups after role-capable server is active. Verify release ancestry, service/timer, unauthenticated denial, three viewer sessions, exports and forbidden writes.

## Review focus

- Cached responses/in-flight fetches must never resurrect a logged-out session.
- Viewer should not continually request proposal/lock endpoints.
- API image and conditional requests require the same identity guard.
- Legacy account configuration and local simulation must remain supported.
- Existing user edits and formal notes must survive publishing.

## Progress ledger

- Initial inspection: existing admin/annotator signed sessions, guest reading allowed, IndexedDB read cache, Markdown export in main.tsx. Existing edits include structured editor and knowledge consolidation; preserved.
- Approved scope includes actual publication and account creation. No additional approval needed for these steps.
- Verification: Python website/roles/proposals/locks suite 120 tests (3 skipped), final auth/sync suite 74 tests (3 skipped); deploy/account/local-sync suite 44 tests passed. Frontend suite passed 188 tests before final shared-card reset regression was added; rerun required after that fix. Production build passed.
- Browser acceptance passed at 390 and 1440 pixels: login-only guest, unknown account rejection, legacy IndexedDB purge, viewer without editing requests, both downloaded formats, logout, cookie expiry/reload, admin role transition under delayed POST plus 61-second timer advance, local anonymous admin/viewer simulation. Screenshots and downloads: temp/private-reader-browser/.
- Review fixed two reproduced races: delayed JSON bodies surviving identity changes, and background auth refresh overriding role switches. Reviewer confirmed both fixes. Additional card-detail cache reset test initially failed; reset subscription now clears shared detail promises on identity changes.
- Ruling: reuse bundled Node Playwright because the Python binding is unavailable; no new dependency installed. Plan/ledger kept in this document to avoid overwriting existing project planning files.
- Final frontend verification after shared-card reset: 49 files, 189 tests passed; production build passed. Existing chunk-size advisory remains. git diff --check clean. Publishing next through the existing script.

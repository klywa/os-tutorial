# Header controls and proposal source navigation

Approved plan: preserve the existing palette and mobile menu; keep account
controls unwrapped and visible; add source navigation to every drawer proposal.
Close only after latest content renders; preserve filters/list offset. Locate
node, insertion anchor, section, then top with a fallback notice. Preserve dirty
drafts/leases on rejection or failure; highlight/focus target for 2.5 seconds.
No commits, pushes or server actions; keep existing unrelated files untouched.

- [x] Account sizing and responsive header.
- [x] Tested target resolution and consistent note/reading preparation.
- [x] Drawer callbacks, persistent state, dirty guards and failure handling.
- [x] Latest reader handoff, DOM focus/highlight and section selection.
- [x] Frontend tests/build, isolated browser/screenshots and independent review.

Ruling: lift drawer state above the keyed ReviewProvider, because note changes
otherwise remount AccountControls and lose filters and list position.
Ruling: prepare matching note/reading revisions before accepting navigation; use
that exact pair in the reader to avoid discarding a draft before a failed load.

Verification:
- RED: new location module absent; GREEN: target ordering and consistent revision
  preparation tests. Complete frontend suite: 153 pass; production build passes.
- Real isolated browser: same/cross-note, approved/pending insert, deleted entry,
  missing chapter/top fallback, focus/highlight timeout, preserved author filter
  and drawer offset, 404, unsaved proposal/main drafts and unchanged leases,
  duplicate clicks, and a main draft created during delayed prefetch all pass.
- Viewports 375/390/430/760/768/1024/1440, long identity/status, public admin and
  annotator, actual local mode, and 125% device-scale layout pass. Screenshots:
  temp/proposal-navigation-browser/. Existing login/locks/mobile suite also passes.
- One independent review identified stale dirty/editing captures after prefetch.
  Fixed by consulting current navigation state; delayed-response browser case
  verifies draft remains. No additional important findings from review.
- Unrelated website-data/usage-matches.json changed concurrently during work and
  was left untouched, as was pre-existing untracked browser_collaboration.cjs.
- No Git commits/pushes, production access, or account/config migrations.

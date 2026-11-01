# Windows local publishing fix

Approved scope: preserve exact website package bytes, use UTF-8 subprocess output,
and show a friendly duplicate-sync message. Keep existing commits and notes; do not
run real publishing, pushes, or production service operations.

## Implementation

- [x] Reproduce six regressions before changing implementation (four package
  verification errors, one output-encoding failure, one duplicate-sync failure).
- [x] Mark website-data recursively as non-text in Git attributes. Clone local
  validation candidates with core.autocrlf=false from the initial checkout.
- [x] Force UTF-8 in child environments while retaining other environment values,
  including background local-service restarts.
- [x] Catch SyncBusy in the CLI without a traceback; retain the lock and refuse
  concurrent work. Never delete the lock or terminate an existing process.
- [x] Complete deployment regression suite and final review.

## Verification ledger

- Six new regression tests RED then GREEN using project Python3.12. Temporary
  repositories exercise global core.autocrlf=true, ordinary Git checkout attributes,
  publish/pull package integrity, corrupt-file rejection, Chinese stdout/stderr,
  and duplicate CLI execution with a real retained lock.
- No repository configuration, existing commits, notes, real remotes or running
  services changed. Existing verification directories remain intact.
- Complete deployment suite:52 tests,51 passed,1 Linux-root ownership test skipped
  on Windows. The duplicate-CLI fixture's ignored FileHandler was replaced with a
  NullHandler; its follow-up regression passes with ResourceWarning treated as an
  error. Python compilation and git diff --check passed.
- Independent final review found no substantiated P1/P2 issues. Real HEAD remains
  316af5f; no real publish/pull script, push or server operation was run.

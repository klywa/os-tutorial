# Follow the deployed Pokilot branch

Evidence: the server screenshot shows master and the updater rejects it solely
because app was hardcoded. Pokilot's original deployment guide uses ordinary
clone/pull and does not mandate app. Local Pokilot is on app, but origin's default
is master and both branches exist. No actual Pokilot branch or configuration was
changed during inspection.

## Decisions and changes

- [x] Preserve the server's named deployment branch and fetch origin/<same-name>.
  When configured, upstream must match that target; reject detached HEAD or
  mismatched/incomplete upstream before fetch or downtime. Do not switch branches,
  change upstream, or merge local app into deployed master.
- [x] Keep the verified fixed SHA, database checks and backups/rollback. Recheck
  both HEAD and branch after stopping before touching serving code.
- [x] Document that Pokilot code must be pushed to the deployed branch. The user
  was offered master/app preference clarification asynchronously; preserve the
  existing master deployment by default without changing production state.
- [x] Complete isolated updater tests and final static verification.

## Verification ledger

RED reproduced master update/no-op rejection, an unchecked mismatched upstream,
and a branch change during stop. Tests include existing app deployments and
master deployments, unchanged skips, detached-head rejection and branch races.
Independent review found no substantiated P1/P2 issues. All operations use
temporary Git origins and mocked services; no real commit/push or server action.
Final updater suite:19 tests,18 passed,1 Linux-root ownership test skipped on
Windows. Python compilation and git diff --check passed. Rollout instructions use
two separate processes: update-sites --os-tutorial first installs the updater,
then update-sites --pokilot loads its new code (an already running old updater
cannot replace its own loaded branch logic midway).

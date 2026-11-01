# Public website restart recovery

Evidence: server journal reports EADDRINUSE on both candidate and rollback
listeners. The old release is active again. Public listeners inherited disabled
address reuse; the health window was30 seconds while observed startup took26s.

## Changes and checks

- [x] Reproduce missing public POSIX socket reuse and rejection of a45s startup
  with isolated sockets and a simulated clock. Windows exclusive binding passes.
- [x] Enable SO_REUSEADDR before binding public POSIX listeners only. Local debug
  and Windows listeners keep their exclusive policy; bind/configure failures close
  the socket.
- [x] Bound public health checks by a monotonic180s deadline and retain rollback.
- [x] Add the one-time first-upgrade option: publish the fix locally, upload the
  installer, run --recover-port. It stops only the website service, waits70s,
  then runs the installer; failures attempt to start the website while retaining
  the original exit status. The old
  publisher already running from the old release cannot use its new health window
  until the first successful activation.
- [x] Relevant HTTP/roles/release regression tests and final review.

## Boundaries

No real commit/push, server access, account change, process termination, or service
operation. Current server status is evidence of rollback, not successful upgrade.
EADDRINUSE is confirmed; TIME_WAIT is the restart mechanism addressed, but the past
socket-owner state cannot be proven from the supplied journal alone.

## Verification

Four targeted cases RED then GREEN (the Windows socket policy is a retained guard).
An actual POSIX TIME_WAIT/rebind test is included but cannot run on this Windows
host; no installed WSL distribution was available. No Linux environment installed.

HTTP/roles/release regression suite:42 tests,40 passed,2 POSIX integration cases
skipped on Windows. Independent review found one P2 in manual stop-before-install
instructions: a pre-activation build failure could leave the site stopped. Fixed
with the guarded recovery option and three shell fixture tests (failure restores
the website with exit7 retained; normal install does not stop the site; unknown
options do not touch services). Mock-command tests reproduced missing recovery and
then passed after the fix. No real system commands or remote operations were run.
Final release/recovery suite:12 passed; Bash syntax, Python compilation and
git diff --check passed.

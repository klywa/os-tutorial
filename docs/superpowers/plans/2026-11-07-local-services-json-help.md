# Local services and JSON help implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. No commits; user expressly prohibited them.

**Goal:** Stable monitored local services plus complete in-app JSON protocol help.
**Architecture:** Durable Node manager owns/observes Python backend and Vite lifecycle; Python controller integrates safe existing lifecycle. Frontend help bundles canonical Markdown and JSON example sources.
**Tech Stack:** Python stdlib, Node stdlib, React19/TypeScript, react-markdown/remark-gfm already installed.
**Spec:** docs/superpowers/specs/2026-11-07-local-services-json-help-design.md

## Global Constraints
- Preserve all current dirty work. No commit, push, public release, OS service or login startup installation.
- Never kill foreign processes or destroy tasks/checkpoints. Local services8765/5173 must survive tool completion.
- No JSON v1 protocol changes; examples cannot overwrite builtin/user events.
- Runtime control secrets/logs/state only in ignored raw; local API additions are backward compatible and absent on public deployment.

## Review Focus
- Explicit stop/publish suspension must not race automatic restart.
- A stale PID or foreign port must not be treated as an owned service.
- Launcher exit must not remove exit diagnostics or supervision.
- Doc optional/default/type semantics must match actual validator/import implementation.
- Help must not accidentally export/import examples into real user data.

## Task1: supervised local runtime
- [x] Add failing isolated lifecycle/state-machine tests for restart backoff1/5/15/60, stable reset, stop/pause/resume, repeated ensure, wrong root and foreign listener.
- [x] Implement deploy/local_supervisor.cjs plus deploy/local_supervisor.py controller and deploy/ensure_local.py CLI; keep Node daemon independent with hidden/detached Windows process and persistent diagnostics.
- [x] Integrate existing deploy/local_sync.py helpers, frontend local status/stop and Vite local control. Preserve legacy fake services/tests; public unaffected.
- [x] Verify dead child restart and direct launcher-exit survival against real disposable processes; run lifecycle/local_sync regressions.
- [x] Restore actual manager/services as soon as task green and start15minute observation while other work proceeds.

## Task2: JSON protocol help
- [x] Extend docs/template-library.md; create independent minimal/complete JSON examples under docs/examples and backend schema/roundtrip tests.
- [x] Build TemplateHelp component from these source files, readable field/operator tables, example copy/download/fallback; add all-role top toolbar entry and compact responsive styles.
- [x] Run frontend tests/build, backend example tests and desktop/mobile browser coverage.

## Task3: integration/review/delivery
- [x] Update AGENTS.md/README with canonical ensure command and mandatory actual endpoint/browser checks, preserving no-publication requirement.
- [x] Independent review of stop/restart races, manager ownership/privacy and schema/docs consistency; fix findings.
- [x] Related Python/deployment/frontend regressions plus help browser acceptance; verify both real endpoints/assets/APIs from independent invocation after startup command exits.
- [x] Observe actual local runtime>=15minutes with timestamped samples, finish with live browser checks, provide addresses and logs. No publish.

## Ownership
- Runtime implementer owns supervisor/controller/CLI, local_sync.py and related tests, local-only server lifecycle hooks and Vite control changes.
- Help implementer owns docs/template-library.md, docs/examples, TemplateHelp.tsx/tests/styles, TemplateLibrary.tsx help wiring, example-validation and isolated help browser tests.
- Parent owns planning records, AGENTS.md/README final workflow, real local startup/observation, integration and review dispatch. Workers do not modify shared planning files or commit.

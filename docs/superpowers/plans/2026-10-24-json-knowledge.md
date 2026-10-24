# JSON Knowledge Implementation Plan

**Goal:** JSON-only canonical knowledge, lossless Markdown export, structured editing and player-grouped navigation.
**Architecture:** A lossless document codec and transactional JSON store replace generated Markdown. Legacy read models are derived in memory for existing filters and source tracking; no legacy full-text index is persisted.
**Tech Stack:** Existing Python workspace/server, React and TypeScript.
**Spec:** User-approved plan in this chat, 2026-10-24.

## Constraints
- Body `.json`; administrative/evidence `.meta.json`; runtime and backup files in raw.
- No knowledge loss, no resurrection of excluded content, preserve manual history and conflicts.
- Whole hero paragraph is one key-value. Hidden key is 正文. Copies use Markdown, without enclosing brackets.
- Player tree contains player note followed by related lineup notes.

## Tasks
- [x] Snapshot existing files, external Markdown edits, reading projections and evidence identities.
- [x] Test and implement lossless nodes, section slicing, key-value serialization and validation.
- [x] Test and implement JSON store, journal recovery, revisions, metadata split and compatibility projections.
- [x] Implement audited migration, explicit branch splitting, links, card conversion and artifact relocation.
- [x] Connect CLI/server/import/create/edit to the new store without Markdown generation.
- [x] Test and implement structured reader/editor, copy/download controls and player directory.
- [x] Update skill contracts and run regression, build, validation and two-entry browser checks.

## Review Focus
- Duplicate keys and repeated paragraphs retain distinct stable identities.
- Markdown fences and nested headings cannot corrupt section boundaries.
- Mid-save crashes never expose mixed body/metadata revisions.
- Old import/recovery paths cannot regenerate Markdown or overwrite manual edits.
- Removing redundant files cannot remove unmerged active knowledge.

## Execution rulings
- Reuse the current clean checkout: production knowledge is local and ignored artifacts would not follow a new worktree.
- Implement inline with one independent final review; the user already approved execution.
- Preserve unrelated source acquisition and raw material.

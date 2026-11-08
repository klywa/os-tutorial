# Template JSON v2 and derived entity monitoring

Approved user plan: portable v2 entity values/suggestions are names, conditions have no IDs, utterances are string lists, no related_entities. Event/group IDs optional; event_name fallback. v1 imports remain compatible; canonical internal v1 stable IDs remain for proposals/sync.

## Work and ownership
- Portable worker: new templates_portable.py and templates_entities.py; isolated converter/matcher tests. Conversion functions decode(document,public,catalog,notes)->canonical v1; encode(public)->portable v2. Does not edit templates_store.py.
- UI/docs worker: frontend components/types/helpers, docs/template-library.md/examples, help tests/browser fixtures. Internal canonical values still {id,name}, conditions/utterances keep IDs; derived_entities read-only snapshot list replaces manually configured related_entities in display. Entity matching resolver used client-side mirrors backend exact name then alias/category policy. Does not edit backend store.
- Parent: store import/export integration, derived bindings/baselines/warnings with archive compatibility, backend tests, final local-service verification.

## Decisions
- Preserve existing checkout and all dirty work; no commit/push/publication.
- Name matching trims whitespace, searches allowed categories, exact names before aliases, matches all same-type versions; absent category with multiple category matches rejects. Unknown values reject atomically.
- Keep domain canonical schema version1; public portable export schema version2. Snapshot/read editor API remains canonical with additional read-only derived_entities; import/preview converts v1/v2 and exports always v2.
- Internal entity reference uses deterministic representative {id,name}; matched ID sets are internal tracked binding metadata for card display and warning history, never portable JSON.
- Actual condition values and scope player derive references; no suggestion/body/manual-only references. Preserve existing retired references and baselines for still-associated entities. Preserve archived manual related_entities data but ignore it for monitoring/UI.
- Stable IDs reuse exact content/order and replacement-block positions; duplicate utterances retained. Event parameter identities reuse key.

## Acceptance
- Converter/matching, import/export roundtrip, duplicate/id stability, v1 compatibility, warning rename/delete/new-version and no unrelated monitoring tests.
- Frontend build/tests and isolated editing/roles/export/help browser tests.
- Independent code review. Unified ensure_local.py --build --restart-backend then independent real8765/5173 pages/assets/API/browser checks. No15-minute observation requirement for this change.

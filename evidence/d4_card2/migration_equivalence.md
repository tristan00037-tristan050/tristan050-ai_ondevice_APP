# D-4 Card 2 Migration Equivalence

STATUS=NEEDS_REVIEW

Base SHA: 25513bf6174d2bed0158e7d2d4a09e70fd678f33
PR #744 previous head: a1c854b27a6a0e04d8eee4affba55d26843b36df
Decision: UI path option A — `apps/butler-tauri/` single path with staged `butler-desktop/` deprecation.

## Phase 1 — Deprecation

- Target: D-4 current PR/hotfix cycle.
- Requirement: keep legacy path working while marking it deprecated.
- Legacy component: `butler-desktop/src/components/chat/DocumentTransformModal.tsx`.
- Legacy route family: `/document_transform/*`.
- New route family: `/api/document_transform/*`.

## Phase 2 — Functional equivalence

Functional equivalence must be proven after GUI T1~T5 PASS.

Required equivalence checks:

1. Card 2 launch from main 8-card grid.
2. Dual upload modal has external document and template zones.
3. 4-step progress is displayed with centered loading.
4. Result has three panes: external summary, mapping, our result.
5. .docx and .md download actions are available.
6. No general chat fallback is exposed inside the Card 2 result area.
7. No raw plaintext is written into evidence.
8. Legacy path remains usable until Phase 3 deletion.

Current result:

- `apps/butler-tauri/src/components/main/CardGrid.tsx`: contract added.
- `apps/butler-tauri/src/components/cards/Card2DocumentTransform.tsx`: contract added.
- `apps/butler-tauri/src/components/cards/Card2Result.tsx`: contract added.
- GUI screenshots: not yet provided.
- Playwright E1~E6: not yet executed.
- Therefore equivalence is not yet PASS.

## Phase 3 — Deletion

Deletion is blocked until Phase 2 PASS.

Do not delete:

- `butler-desktop/src/components/chat/DocumentTransformModal.tsx`
- legacy `/document_transform/*` routes

until D-4 GUI T1~T5 and sidecar endpoint ping evidence are present.

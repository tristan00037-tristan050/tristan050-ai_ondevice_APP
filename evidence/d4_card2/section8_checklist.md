# D-4 Card 2 §8 Checklist

STATUS=NEEDS_REVIEW

Base SHA: 25513bf6174d2bed0158e7d2d4a09e70fd678f33
Directive: D4_CARD2_DOCUMENT_TRANSFORM_v1_1

## §8.1 Main screen integration

- Status: PARTIAL
- Evidence: `apps/butler-tauri/src/components/main/CardGrid.tsx`
- Notes: v1.1 contract component added. Existing production UI still uses `butler-desktop/src/components/chat/EmptyState.tsx`; final integration verification required.

## §8.2 Modal entry routing

- Status: PARTIAL
- Evidence: `apps/butler-tauri/src/components/cards/Card2DocumentTransform.tsx`
- Notes: dual upload modal contract added. Runtime route integration still requires GUI verification.

## §8.3 UX consistency

- Status: PARTIAL
- Evidence: Card2 modal uses 240px upload boxes, full-width primary action, 18px header.
- Notes: Playwright E1~E3 not executed in this environment.

## §8.4 Lucide icons only

- Status: PARTIAL
- Evidence: new v1.1 files import Lucide React components only.
- Notes: full repository emoji grep not executed here; must run before merge.

## §8.5 4-step progress UI

- Status: PARTIAL
- Evidence: `Card2DocumentTransform.tsx` contains four steps and progress bar.
- Notes: SSE integration pending endpoint alias implementation.

## §8.6 Result tri-pane + GUI DoD

- Status: PARTIAL
- Evidence: `Card2Result.tsx`
- Notes: GUI T1~T5 screenshots are not generated; manual representative verification required.

## §8.7 sidecar ready check and endpoint timeout

- Status: PARTIAL
- Evidence: `butler_pc_core/document_transform/api_contract_v1_1.py`
- Notes: v1.1 contract defines 60s endpoints and 180s SSE. Actual FastAPI route alias integration not yet verified.

## §8.8 Dependency files

- Status: NEEDS_REVIEW
- Evidence: No dependency change committed in this PR.
- Notes: Existing dependencies may already include required packages; dependency audit required.

## §8.9 E2E verification

- Status: BLOCK
- Evidence: `evidence/d4_card2/playwright_e2e.log`
- Notes: Playwright E1~E6 not executed by this assistant environment.

## §8.10 General chat fallback blocked

- Status: NEEDS_REVIEW
- Evidence: Card2 result component has no chat fallback entry.
- Notes: full UI flow grep and GUI verification required.

# Day 4 Progress — Tauri Desktop UI

**Date:** 2026-04-30  
**Branch:** feature/day4-tauri-ui-cards-egress

## Completed Tasks

### 1. Vitest Setup (butler-desktop)
- `package.json`, `vite.config.ts`, `tsconfig.json` configured
- `src/test-setup.ts`: `@testing-library/jest-dom/vitest` + `afterEach(cleanup)` + jsdom stubs for `URL.createObjectURL` / `URL.revokeObjectURL`

### 2. Components (4)

| Component | File | Key features |
|-----------|------|-------------|
| `HomeScreen` | `src/components/HomeScreen.tsx` | 6 fixed cards, keyboard nav, bank-upload-guide (card 5), free-input-placeholder |
| `EgressBadge` | `src/components/EgressBadge.tsx` | Local-only badge, detail panel, JSON download, blocked state (#f5222d) |
| `InputBar` | `src/components/InputBar.tsx` | Text/file/voice, /api/precheck, XL/blocked Team Hub guide, maxLength=4000 |
| `ProgressOverlay` | `src/components/ProgressOverlay.tsx` | 9 SSE event types, progress bar, cancel, partial-result button |

### 3. Tests — 21/21 PASS

```
 ✓ src/__tests__/ProgressOverlay.test.tsx  (6 tests)
 ✓ src/__tests__/EgressBadge.test.tsx      (5 tests)
 ✓ src/__tests__/InputBar.test.tsx         (5 tests)
 ✓ src/__tests__/HomeScreen.test.tsx       (5 tests)
 Tests  21 passed (21)
```

### 4. Tauri Debug Build

```
Finished `dev` profile [unoptimized + debuginfo] target(s) in 4.09s
Built application at: src-tauri/target/debug/butler-desktop
Bundling Butler.app → src-tauri/target/debug/bundle/macos/Butler.app
Bundling Butler_0.1.0_aarch64.dmg → .../bundle/dmg/Butler_0.1.0_aarch64.dmg
Finished 2 bundles
```

Full log: `evidence/day4_tauri_build.log`

## Key Issues Fixed

| Issue | Fix |
|-------|-----|
| `expect is not defined` in Vitest | Changed to `@testing-library/jest-dom/vitest` entry point |
| DOM not cleaned between tests | Added `afterEach(cleanup)` to test-setup.ts |
| `URL.createObjectURL does not exist` (jsdom) | Added global stubs in test-setup.ts; use `vi.mocked()` |
| Recursive `createElement` mock stack overflow | Use `HTMLAnchorElement.prototype.click` spy instead |
| `HomeScreen onSubmit` type mismatch in App.tsx | Removed wrong prop pass (`onSubmit` signature differs) |
| Tauri icon not found / not RGBA | Generated 32×32 / 128×128 RGBA PNG stubs in `src-tauri/icons/` |

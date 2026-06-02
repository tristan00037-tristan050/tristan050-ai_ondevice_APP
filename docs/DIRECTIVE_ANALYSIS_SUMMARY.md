# Butler Box 3 v1.2 Directive Analysis Summary

The attached directive was interpreted as a safety-critical contract package,
not as a real model integration package.

## Key Corrections Reflected

1. Display SHA prefixes are never treated as sealed hashes.
2. Missing helper4/helper7/helper8 asset evidence blocks real claim.
3. Current main endpoint is kept as `/v1/cards/3/draft`.
4. Multi-document UI input is mapped to digest-only current contract input.
5. Grounding failure cannot be hidden behind a draft pass.
6. Receipt remains a hook only.
7. Evaluation is verdict-only and digest-safe.
8. State gates are explicit and monotonic.

## Enhancement Added

- Digest-aware PII scanner avoids false positives on `sha256:<64hex>` while
  still catching email, Korean RRN, phone, card/account, secrets, and local
  paths in raw runtime text.
- Tests prove both positive guard behavior and digest false-positive suppression.
- Evaluation summary explicitly separates digest-safe proxy metrics from real
  rewrite quality measurement.


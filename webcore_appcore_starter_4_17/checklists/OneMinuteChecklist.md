# App Core QuickCheck — One Minute Checklist

- [ ] Feature flags: App QuickCheck HUD/Reporter OFF in prod, ON in dev/stg.
- [ ] Policy JSON validates against `contracts/qc_policy.schema.json`.
- [ ] Gate: `app_quickcheck_gate.mjs --policy ./configs/app_qc_policy.json` blocks `severity=block` rules.
- [ ] Report: JSON keys ordered (status,diff,policy,notes,raw); MD includes Status→Diff→Policy→Notes.
- [ ] Redaction: rules loaded; over-redaction guard enabled (80%).
- [ ] Labels only `decision|ok` present in emitted metrics.

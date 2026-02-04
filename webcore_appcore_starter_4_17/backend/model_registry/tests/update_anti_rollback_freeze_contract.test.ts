import { enforceAntiRollbackFreeze } from "../verify/update_anti_rollback_freeze";

test("[EVID:ANTI_ROLLBACK_ENFORCED_OK] lower version must be rejected", () => {
  const now = 1_700_000_000_000;
  expect(() =>
    enforceAntiRollbackFreeze({
      incomingVersion: 4,
      maxSeenVersion: 5,
      expiresAtMs: now + 60_000,
      nowMs: now,
    })
  ).toThrow(/ANTI_ROLLBACK/);
});

test("[EVID:ANTI_FREEZE_EXPIRES_ENFORCED_OK] expired metadata must be rejected", () => {
  const now = 1_700_000_000_000;
  expect(() =>
    enforceAntiRollbackFreeze({
      incomingVersion: 6,
      maxSeenVersion: 5,
      expiresAtMs: now - 1,
      nowMs: now,
    })
  ).toThrow(/ANTI_FREEZE/);
});

test("non-expired and non-rollback must pass", () => {
  const now = 1_700_000_000_000;
  expect(() =>
    enforceAntiRollbackFreeze({
      incomingVersion: 5,
      maxSeenVersion: 5,
      expiresAtMs: now + 1,
      nowMs: now,
    })
  ).not.toThrow();
});


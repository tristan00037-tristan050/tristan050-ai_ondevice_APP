import { validateMetaOnlyWithSSOT, type MetaOnlySSOT } from "../../../../shared/meta_only/validator_core";

// Client-side helper: caller must pass SSOT object (how it is obtained is product flow specific)
export function validateMetaOnlyClient(payload: any, ssot: MetaOnlySSOT) {
  return validateMetaOnlyWithSSOT(payload, ssot);
}

export type IP3DryRunResult = {
  routing_state: 'dry_run' | 'blocked' | 'fallback' | 'failed_closed';
  actual_model_call: false;
  production_hook_deployed: false;
  release_claim_allowed: false;
  request_digest?: string;
  audit_digest?: string;
  sample_replay: Record<string, unknown>;
  block_message: string;
};

const BLOCK_MESSAGE = '현재 sample replay 모드. live 진입 시 IP1 v5.4 forward evidence + IP2 v2.4 live PEP 의무.';

export async function requestIP3DryRun(messages: Array<{ role: 'user'; content: string }>, modelId = 'butler-1.7b-v4-rt-q4_k_m'): Promise<IP3DryRunResult> {
  const response = await fetch('http://127.0.0.1:8765/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, messages, routing_context: { evidence_class: 'sample', ui_dry_run: true } }),
  });

  if (!response.ok) {
    return {
      routing_state: 'blocked',
      actual_model_call: false,
      production_hook_deployed: false,
      release_claim_allowed: false,
      sample_replay: {},
      block_message: BLOCK_MESSAGE,
    };
  }

  const data = await response.json();
  const routing = data.ip3_routing ?? {};
  return {
    routing_state: routing.routing_state ?? 'dry_run',
    actual_model_call: false,
    production_hook_deployed: false,
    release_claim_allowed: false,
    request_digest: routing.request_digest,
    audit_digest: routing.audit_digest,
    sample_replay: data.sample_replay ?? {},
    block_message: routing.block_message ?? BLOCK_MESSAGE,
  };
}

export function box2SampleReplay() {
  return {
    document_type: 'company_form_sample',
    issued_date: 'sample_date_digest_only',
    owner: 'sample_owner_digest_only',
    agreements: ['sample_agreement_digest_only'],
    contract_amount: 'sample_amount_digest_only',
  };
}

export function box3SampleReplay() {
  return {
    action: 'draft_review_request',
    approval_required_text: '반드시 우리 승인 후',
    actual_model_call: false,
  };
}

export { BLOCK_MESSAGE };

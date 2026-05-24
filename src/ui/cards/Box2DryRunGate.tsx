import React, { useState } from 'react';
import { BLOCK_MESSAGE, box2SampleReplay, requestIP3DryRun, type IP3DryRunResult } from './ip3DryRunClient';

const BOX2_ADAPTER_SHA = '92e8454fdc01d9bb000000000000000000000000000000000000000000000000';
const BOX2_BLOCK_MESSAGE = '현재 sample replay 모드. live 진입 시 IP1 v5.4 forward evidence + IP2 v2.4 live PEP 의무.';

export function Box2DryRunGate() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<IP3DryRunResult | null>(null);

  async function runDryRun() {
    const response = await requestIP3DryRun([{ role: 'user', content: input }]);
    setResult({ ...response, sample_replay: box2SampleReplay() });
  }

  return (
    <section data-testid="ip3-box2-dry-run" aria-label="Box 2 dry run gate">
      <h3>양식 도우미 — sample replay</h3>
      <p>Adapter SHA: <code>{BOX2_ADAPTER_SHA}</code></p>
      <p>actual_model_call=false</p>
      <p>production_hook_deployed=false</p>
      <p>release_claim_allowed=false</p>
      <textarea aria-label="외부 문서 입력" value={input} onChange={event => setInput(event.target.value)} />
      <button type="button" onClick={runDryRun}>dry_run 확인</button>
      <p role="status">{result?.routing_state ?? 'dry_run 대기'}</p>
      <pre>{JSON.stringify(result?.sample_replay ?? box2SampleReplay(), null, 2)}</pre>
      <p>{result?.block_message ?? BLOCK_MESSAGE}</p>
      <p>{BOX2_BLOCK_MESSAGE}</p>
    </section>
  );
}

export { BOX2_ADAPTER_SHA, BOX2_BLOCK_MESSAGE };

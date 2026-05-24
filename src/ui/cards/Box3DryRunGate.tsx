import React, { useState } from 'react';
import { BLOCK_MESSAGE, box3SampleReplay, requestIP3DryRun, type IP3DryRunResult } from './ip3DryRunClient';

const BOX3_ADAPTER_SHA = 'ad852bbb79aee63c000000000000000000000000000000000000000000000000';
const BOX3_APPROVAL_COPY = '반드시 우리 승인 후';

export function Box3DryRunGate() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<IP3DryRunResult | null>(null);

  async function runDryRun() {
    const response = await requestIP3DryRun([{ role: 'user', content: input }]);
    setResult({ ...response, sample_replay: box3SampleReplay() });
  }

  return (
    <section data-testid="ip3-box3-dry-run" aria-label="Box 3 dry run gate">
      <h3>말뜻 알아채기 도우미 — sample replay</h3>
      <p>Adapter SHA: <code>{BOX3_ADAPTER_SHA}</code></p>
      <p>actual_model_call=false</p>
      <p>production_hook_deployed=false</p>
      <p>release_claim_allowed=false</p>
      <textarea aria-label="자연어 요청 입력" value={input} onChange={event => setInput(event.target.value)} />
      <button type="button" onClick={runDryRun}>dry_run 확인</button>
      <p role="status">{result?.routing_state ?? 'dry_run 대기'}</p>
      <pre>{JSON.stringify(result?.sample_replay ?? box3SampleReplay(), null, 2)}</pre>
      <p>{BOX3_APPROVAL_COPY}</p>
      <p>{result?.block_message ?? BLOCK_MESSAGE}</p>
    </section>
  );
}

export { BOX3_ADAPTER_SHA, BOX3_APPROVAL_COPY };

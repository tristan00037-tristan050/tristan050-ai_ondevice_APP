// AI-ALGO: TOKENIZER_CONTRACT_V1
// 알고리즘팀 산출물 — tokenizer 계약 (chat_template 필수, digest 검증)

export interface TokenizerContractV1 {
  logical_pack_id: string;
  tokenizer_json_digest_sha256: string;
  chat_template_digest_sha256: string;
  chat_template_required: true;
  vocab_size: number;
  bos_token_id: number | null;
  eos_token_id: number | number[] | null;
  pad_token_id: number | null;
}

export function assertTokenizerContractV1(c: unknown): asserts c is TokenizerContractV1 {
  if (!c || typeof c !== 'object') throw new Error('TOKENIZER_CONTRACT_NOT_OBJECT');
  const t = c as Record<string, unknown>;
  if (typeof t['logical_pack_id'] !== 'string' || !t['logical_pack_id'])
    throw new Error('TOKENIZER_CONTRACT_MISSING:logical_pack_id');
  if (typeof t['tokenizer_json_digest_sha256'] !== 'string' || !/^[0-9a-f]{64}$/.test(t['tokenizer_json_digest_sha256'] as string))
    throw new Error('TOKENIZER_CONTRACT_INVALID:tokenizer_json_digest_sha256');
  if (typeof t['chat_template_digest_sha256'] !== 'string' || !/^[0-9a-f]{64}$/.test(t['chat_template_digest_sha256'] as string))
    throw new Error('TOKENIZER_CONTRACT_INVALID:chat_template_digest_sha256');
  if (t['chat_template_required'] !== true)
    throw new Error('TOKENIZER_CONTRACT_CHAT_TEMPLATE_REQUIRED_MISSING');
  if (typeof t['vocab_size'] !== 'number' || t['vocab_size'] <= 0)
    throw new Error('TOKENIZER_CONTRACT_INVALID:vocab_size');
}

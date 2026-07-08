export class AnalyzeStreamResultError extends Error {
  constructor() {
    super('결과 형식을 확인하지 못했습니다.');
    this.name = 'AnalyzeStreamResultError';
  }
}

type ResultValidator<T> = (value: unknown) => T | null;

function safeJsonParse(text: string): unknown | null {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function stripCodeFence(text: string): string {
  const trimmed = text.trim();
  const fence = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return fence ? fence[1].trim() : trimmed;
}

function extractFirstJsonObject(text: string): unknown | null {
  const source = stripCodeFence(text);
  if (!source) return null;
  const direct = safeJsonParse(source);
  if (direct !== null) return direct;

  const start = source.indexOf('{');
  if (start < 0) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < source.length; i += 1) {
    const char = source[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
    } else if (char === '{') {
      depth += 1;
    } else if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return safeJsonParse(source.slice(start, i + 1));
      }
    }
  }
  return null;
}

function collectSseDataObjects(text: string): unknown[] {
  const blocks = text.split(/\r?\n\r?\n/);
  const values: unknown[] = [];
  for (const block of blocks) {
    const dataLines = block
      .split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trim());
    if (!dataLines.length) continue;
    const parsed = safeJsonParse(dataLines.join('\n'));
    if (parsed !== null) values.push(parsed);
  }
  return values;
}

function expandCandidate(value: unknown): unknown[] {
  const candidates: unknown[] = [value];
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of ['result_text', 'result', 'data', 'payload']) {
      const nested = record[key];
      if (typeof nested === 'string') {
        const parsed = extractFirstJsonObject(nested);
        if (parsed !== null) candidates.push(parsed);
      } else if (nested && typeof nested === 'object') {
        candidates.push(nested);
      }
    }
  } else if (typeof value === 'string') {
    const parsed = extractFirstJsonObject(value);
    if (parsed !== null) candidates.push(parsed);
  }
  return candidates;
}

export function parseAnalyzeStreamResult<T>(body: string, validate: ResultValidator<T>): T {
  const roots: unknown[] = [];
  roots.push(...collectSseDataObjects(body));
  const whole = extractFirstJsonObject(body);
  if (whole !== null) roots.push(whole);

  for (let i = roots.length - 1; i >= 0; i -= 1) {
    for (const candidate of expandCandidate(roots[i])) {
      const result = validate(candidate);
      if (result) return result;
    }
  }

  throw new AnalyzeStreamResultError();
}


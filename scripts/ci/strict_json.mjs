import { lstat, readFile } from 'node:fs/promises';

export class StrictJsonError extends Error {}

class Parser {
  constructor(text, options) {
    this.text = text;
    this.index = 0;
    this.nodes = 0;
    this.maxDepth = options.maxDepth;
    this.maxNodes = options.maxNodes;
    this.maxStringChars = options.maxStringChars;
  }

  fail(code) {
    throw new StrictJsonError(code);
  }

  whitespace() {
    while (/[\t\n\r ]/.test(this.text[this.index] ?? '')) this.index += 1;
  }

  node(depth) {
    this.nodes += 1;
    if (this.nodes > this.maxNodes) this.fail('JSON_TOO_COMPLEX');
    if (depth > this.maxDepth) this.fail('JSON_TOO_DEEP');
  }

  string() {
    if (this.text[this.index] !== '"') this.fail('JSON_STRING_EXPECTED');
    const start = this.index;
    this.index += 1;
    let escaped = false;
    while (this.index < this.text.length) {
      const code = this.text.charCodeAt(this.index);
      const char = this.text[this.index];
      if (!escaped && char === '"') {
        this.index += 1;
        let value;
        try {
          value = JSON.parse(this.text.slice(start, this.index));
        } catch {
          this.fail('JSON_STRING_INVALID');
        }
        if (value.length > this.maxStringChars) this.fail('JSON_STRING_TOO_LONG');
        for (let offset = 0; offset < value.length; offset += 1) {
          const unit = value.charCodeAt(offset);
          if (unit >= 0xd800 && unit <= 0xdbff) {
            const next = value.charCodeAt(offset + 1);
            if (!(next >= 0xdc00 && next <= 0xdfff)) {
              this.fail('JSON_UNPAIRED_SURROGATE');
            }
            offset += 1;
          } else if (unit >= 0xdc00 && unit <= 0xdfff) {
            this.fail('JSON_UNPAIRED_SURROGATE');
          }
        }
        return value;
      }
      if (!escaped && code < 0x20) this.fail('JSON_STRING_INVALID');
      if (!escaped && char === '\\') escaped = true;
      else escaped = false;
      this.index += 1;
    }
    this.fail('JSON_STRING_INVALID');
  }

  value(depth = 1) {
    this.whitespace();
    this.node(depth);
    const char = this.text[this.index];
    if (char === '{') return this.object(depth);
    if (char === '[') return this.array(depth);
    if (char === '"') return this.string();
    for (const [literal, value] of [
      ['true', true],
      ['false', false],
      ['null', null],
    ]) {
      if (this.text.startsWith(literal, this.index)) {
        this.index += literal.length;
        return value;
      }
    }
    const match = this.text.slice(this.index).match(
      /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/,
    );
    if (!match) this.fail('JSON_VALUE_INVALID');
    this.index += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) this.fail('JSON_NUMBER_INVALID');
    if (!match[0].includes('.') && !/[eE]/.test(match[0])
        && !Number.isSafeInteger(value)) {
      this.fail('JSON_INTEGER_UNSAFE');
    }
    return value;
  }

  object(depth) {
    this.index += 1;
    const value = {};
    const keys = new Set();
    this.whitespace();
    if (this.text[this.index] === '}') {
      this.index += 1;
      return value;
    }
    while (this.index < this.text.length) {
      this.whitespace();
      const key = this.string();
      if (keys.has(key)) this.fail('JSON_DUPLICATE_KEY');
      keys.add(key);
      this.whitespace();
      if (this.text[this.index] !== ':') this.fail('JSON_COLON_EXPECTED');
      this.index += 1;
      value[key] = this.value(depth + 1);
      this.whitespace();
      const separator = this.text[this.index];
      this.index += 1;
      if (separator === '}') return value;
      if (separator !== ',') this.fail('JSON_OBJECT_SEPARATOR_INVALID');
    }
    this.fail('JSON_OBJECT_INVALID');
  }

  array(depth) {
    this.index += 1;
    const value = [];
    this.whitespace();
    if (this.text[this.index] === ']') {
      this.index += 1;
      return value;
    }
    while (this.index < this.text.length) {
      value.push(this.value(depth + 1));
      this.whitespace();
      const separator = this.text[this.index];
      this.index += 1;
      if (separator === ']') return value;
      if (separator !== ',') this.fail('JSON_ARRAY_SEPARATOR_INVALID');
    }
    this.fail('JSON_ARRAY_INVALID');
  }

  parse() {
    const value = this.value();
    this.whitespace();
    if (this.index !== this.text.length) this.fail('JSON_TRAILING_DATA');
    return value;
  }
}

export function parseStrictJson(
  raw,
  {
    maxBytes = 64 * 1024,
    maxDepth = 32,
    maxNodes = 1_000_000,
    maxStringChars = 1_000_000,
    requireObject = true,
  } = {},
) {
  const bytes = Buffer.isBuffer(raw) ? raw : Buffer.from(raw);
  if (bytes.length > maxBytes) throw new StrictJsonError('JSON_TOO_LARGE');
  let text;
  try {
    text = new TextDecoder(
      'utf-8',
      { fatal: true, ignoreBOM: true },
    ).decode(bytes);
  } catch {
    throw new StrictJsonError('JSON_UTF8_INVALID');
  }
  if (text.startsWith('\ufeff')) throw new StrictJsonError('JSON_BOM_FORBIDDEN');
  const value = new Parser(text, {
    maxDepth,
    maxNodes,
    maxStringChars,
  }).parse();
  if (requireObject && (typeof value !== 'object' || value === null
      || Array.isArray(value))) {
    throw new StrictJsonError('JSON_ROOT_NOT_OBJECT');
  }
  return value;
}

export async function readStrictJsonFile(
  path,
  options = {},
) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new StrictJsonError('JSON_FILE_TYPE_INVALID');
  }
  const maxBytes = options.maxBytes ?? 64 * 1024;
  if (metadata.size > maxBytes) throw new StrictJsonError('JSON_TOO_LARGE');
  return parseStrictJson(await readFile(path), options);
}

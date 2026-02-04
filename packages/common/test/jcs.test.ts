import { jcsCanonicalize } from "../src/crypto/jcs";

test("JCS: deterministic key ordering", () => {
  const a = { b: 1, a: 2 };
  const b = { a: 2, b: 1 };
  expect(jcsCanonicalize(a)).toBe(jcsCanonicalize(b));
  expect(jcsCanonicalize(a)).toBe('{"a":2,"b":1}');
});

test("JCS: unicode and escapes preserved by JSON.stringify", () => {
  const v = { t: "A\u0000B", u: "가" };
  expect(jcsCanonicalize(v)).toBe('{"t":"A\\u0000B","u":"가"}');
});

test("JCS: arrays and nested objects", () => {
  const v = { z: [3, { y: 2, x: 1 }], a: true };
  expect(jcsCanonicalize(v)).toBe('{"a":true,"z":[3,{"x":1,"y":2}]}');
});

test("JCS: reject NaN/Infinity", () => {
  expect(() => jcsCanonicalize({ n: NaN })).toThrow();
  expect(() => jcsCanonicalize({ n: Infinity })).toThrow();
});


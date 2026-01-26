"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.canonicalizeJson = canonicalizeJson;
/**
 * Minimal JCS-like canonicalization (stable JSON stringify).
 * Note: This is a deterministic stringify to remove key-order ambiguity.
 * Hardening 목표: server/tests/sdk가 동일 구현을 공유하는 것.
 */
function canonicalizeJson(input) {
    return JSON.stringify(sortRec(input));
}
function sortRec(x) {
    if (x === null || x === undefined)
        return x;
    if (Array.isArray(x))
        return x.map(sortRec);
    if (typeof x === "object") {
        const keys = Object.keys(x).sort();
        const out = {};
        for (const k of keys)
            out[k] = sortRec(x[k]);
        return out;
    }
    return x;
}

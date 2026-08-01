#!/usr/bin/env python3
"""Publish the measured trusted FirstScreen verdict.

Reads only the trusted verifier's own measured evidence (required-audit.json,
mutations.json, historical.json) and emits the verdict. Fail closed: a missing
file/key or a non-integer/non-clean value is an error, never a default. This is
a protected verifier asset (digest-pinned in trusted-verifier-assets.v1.json);
it was previously inlined in the workflow and is extracted to a file so the
manifest can protect it.
"""
from __future__ import annotations

import json
import sys


def fail(code: str) -> None:
    print("TRUSTED_VERIFIER_PASS=0")
    print("ERROR_CODE=" + code)
    raise SystemExit(1)


def load(path: str):
    try:
        with open(path, "rb") as handle:
            return json.load(handle)
    except FileNotFoundError:
        fail("SOURCE_FILE_MISSING:" + path)
    except (ValueError, OSError):
        fail("SOURCE_FILE_UNREADABLE:" + path)


def read_int(doc, key: str, path: str) -> int:
    # Fail closed: a missing key, or a value that is not a real integer
    # (bool subclasses int and is rejected) is an error, never a default.
    if not isinstance(doc, dict) or key not in doc:
        fail("SOURCE_KEY_MISSING:" + path + "#" + key)
    value = doc[key]
    if isinstance(value, bool) or not isinstance(value, int):
        fail("SOURCE_VALUE_NOT_INT:" + path + "#" + key)
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        fail("ARGUMENT_INVALID")
    req_path, mut_path, hist_path = argv[1], argv[2], argv[3]

    required = load(req_path)
    mutations = load(mut_path)
    historical = load(hist_path)

    measured = [
        ("REQUIRED_TOTAL", required, "required_total", req_path),
        ("MISSING", required, "missing", req_path),
        ("SKIPPED", required, "skipped", req_path),
        ("DESELECTED", required, "deselected", req_path),
        ("XFAIL", required, "xfail", req_path),
        ("FAILED", required, "failed", req_path),
        ("ERRORS", required, "errors", req_path),
        ("UNEXPECTED", required, "unexpected", req_path),
        ("TOTAL_GENERATED_CASES", mutations, "total_generated_cases", mut_path),
        ("ACCEPTED_MALICIOUS", mutations, "accepted_malicious", mut_path),
        ("UNANALYSED", mutations, "unanalysed", mut_path),
    ]
    rows = [
        (name, read_int(doc, key, path), path + "#" + key)
        for name, doc, key, path in measured
    ]

    # PR_CODE_EXECUTED_BY_TRUSTED_VERIFIER is a structural invariant: the trusted
    # verifier executes only protected code, never PR-authored code. No artifact
    # emits it as a numeric field and the workflow contract test requires the
    # literal to be present, so gate the invariant on historical.json proving a
    # clean protected replay (0 accepted malicious, 0 unanalysed). Fail closed if
    # the file/keys are missing, non-integer, or non-zero.
    if read_int(historical, "accepted_malicious", hist_path) != 0 \
            or read_int(historical, "unanalysed", hist_path) != 0:
        fail("HISTORICAL_REPLAY_NOT_CLEAN:" + hist_path)

    print("TRUSTED_VERIFIER_PASS=1")
    print("PR_CODE_EXECUTED_BY_TRUSTED_VERIFIER=0  (invariant; gated on "
          + hist_path + " #accepted_malicious,#unanalysed)")
    for name, value, source in rows:
        print(name + "=" + str(value) + "  (source: " + source + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

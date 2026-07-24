# Proposal: split llama-grammar coverage into a dedicated runtime job

## Problem
`firstscreen-v2-5-product-gate → repository-python` installs
`requirements-firstscreen-ci.lock`, which **deliberately excludes**
`llama-cpp-python` (heavy native runtime) to stay fast and deterministic.

28 box4/box6/card/runtime tests require the llama-cpp **grammar** runtime to
produce structured output; without it `butler_pc_core.runtime.json_grammar`
raises `GrammarUnavailable("LLAMA_GRAMMAR_IMPORT_FAILED")` and the services
fail-closed, so those tests cannot reach their intended assertions.

These are now marked `@pytest.mark.requires_llama_grammar` and **skip with a
visible reason** in the torch/llama-free job (they are not fake-passed). But
skipping them there means box4/box6 structured-output contracts are not verified
on that job. To keep them a **required** check, run them in a job that has the
runtime.

## Proposed job (draft)
```yaml
  repository-python-grammar:
    runs-on: ubuntu-latest
    needs: scope-and-contracts
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with: {fetch-depth: 0}
      - uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0
        with:
          python-version: ${{ env.PYTHON_VERSION }}   # 3.12
          cache: pip
          cache-dependency-path: requirements-firstscreen-ci-grammar.lock
      - run: python -m pip install --require-hashes -r requirements-firstscreen-ci-grammar.lock
      # `-m` only SELECTS tests to run; pytest still COLLECTS/imports all of
      # tests/ first, so carry the same ignores as repository-python (turboq/eval
      # would otherwise fail collection before the grammar-marked tests run).
      - run: >
          python -m pytest tests/ -q -m requires_llama_grammar
          --ignore=tests/turboq/
          --ignore=tests/eval/test_eval_hardcase.py
          --ignore=tests/eval/test_eval_judge_v3.py
          --junitxml=repository-grammar-junit.xml
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always()   # keep JUnit on failure too
        with: {name: firstscreen-v2-5-repository-grammar, path: repository-grammar-junit.xml, if-no-files-found: error}
```
Then add `repository-python-grammar` to the `gate` job's `needs:` so it is required.

## Lock delta (draft)
Create `requirements-firstscreen-ci-grammar.lock` = `requirements-firstscreen-ci.lock`
**plus** a hash-pinned CPU build of `llama-cpp-python` and its transitive deps, e.g.:
```
# generated via: pip-compile --generate-hashes (CPU-only extra index)
llama-cpp-python==<pin> \
    --hash=sha256:<...>
# + diskcache, jinja2 (already present), numpy (already present), typing-extensions ...
```
(The exact pin/hashes must be produced with `pip-compile --generate-hashes` on a
Linux/py3.12 runner with the CPU wheel index; that cannot be hand-authored here.)

## Note
`requires_llama_grammar` is registered in `tests/conftest.py::pytest_configure`
and honored by `pytest_collection_modifyitems` (skip-if-unavailable). The same
28 tests run for real once the runtime is present — no coverage is silently
dropped, it is relocated to a runtime-appropriate required job.

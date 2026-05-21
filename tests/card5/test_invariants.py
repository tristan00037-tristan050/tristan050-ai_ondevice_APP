import pytest

from butler.card5.invariants import Invariants, verify_invariants


def test_default_invariants_pass():
    verify_invariants()


def test_base_model_changed_fails():
    with pytest.raises(RuntimeError, match="base_model_changed"):
        verify_invariants(Invariants(base_model_changed=True))


def test_tokenizer_changed_fails():
    with pytest.raises(RuntimeError, match="tokenizer_changed"):
        verify_invariants(Invariants(tokenizer_changed=True))


def test_data_117_used_fails():
    with pytest.raises(RuntimeError, match="data_117"):
        verify_invariants(Invariants(data_117_used_zero=False))

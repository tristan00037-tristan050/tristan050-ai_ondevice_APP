from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any, TypeVar

from .errors import PolicyLoadError

K = TypeVar("K")
V = TypeVar("V")


class FrozenPolicyMap(Mapping[K, V]):
    """Deeply immutable mapping with a stable mutation failure contract."""

    __slots__ = ("__data",)

    def __init__(self, data: Mapping[K, V]):
        object.__setattr__(self, "_FrozenPolicyMap__data", MappingProxyType(dict(data)))

    def __getitem__(self, key: K) -> V:
        return self.__data[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __setitem__(self, _key: K, _value: V) -> None:
        raise PolicyLoadError("POLICY_IMMUTABLE", "MUTATION_ATTEMPT")

    def __delitem__(self, _key: K) -> None:
        raise PolicyLoadError("POLICY_IMMUTABLE", "MUTATION_ATTEMPT")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise PolicyLoadError("POLICY_IMMUTABLE", "MUTATION_ATTEMPT")

    def __repr__(self) -> str:
        return f"FrozenPolicyMap(keys={tuple(self.__data)})"


def deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenPolicyMap({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    return value

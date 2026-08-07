from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def helper1_v51_vector_root() -> Path:
    return Path(__file__).with_name("vectors")

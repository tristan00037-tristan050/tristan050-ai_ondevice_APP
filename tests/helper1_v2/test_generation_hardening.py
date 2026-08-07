from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from butler_pc_core.helper1.index_store import EncryptedGenerationStore, IndexStoreError
from butler_pc_core.helper1.security import MemoryKeyProvider
from tests.helper1_v2.test_product_pipeline import _digest, _publish


@pytest.fixture
def generation_store(tmp_path):
    root = tmp_path / "index"
    root.mkdir(mode=0o700)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    store = EncryptedGenerationStore(fd, MemoryKeyProvider(root=b"k" * 32))
    try:
        yield store, root
    finally:
        os.close(fd)


def test_publish_rejects_tampered_current_generation(generation_store):
    store, root = generation_store
    workspace_id = str(uuid.uuid4())
    manifest, _ = _publish(store, workspace_id)
    target = root / f"gen-{manifest.generation_id}" / "manifest.sig"
    signature = json.loads(target.read_text(encoding="utf-8"))
    signature["signature_sha256"] = _digest("forged")
    target.write_text(json.dumps(signature), encoding="utf-8")

    with pytest.raises(IndexStoreError, match="INDEX_SIGNATURE_INVALID"):
        _publish(
            store,
            workspace_id,
            previous_generation_id=manifest.generation_id,
        )


def test_publish_recovers_valid_crash_debris(generation_store):
    store, root = generation_store
    stage_id = str(uuid.uuid4())
    pointer_id = str(uuid.uuid4())
    (root / f".stage-{stage_id}").mkdir()
    (root / f".stage-{stage_id}" / "partial").write_bytes(b"partial")
    (root / f".current-{pointer_id}").write_text(pointer_id + "\n", encoding="ascii")

    manifest, _ = _publish(store, str(uuid.uuid4()))

    assert manifest.previous_generation_id is None
    assert not (root / f".stage-{stage_id}").exists()
    assert not (root / f".current-{pointer_id}").exists()


def test_concurrent_publish_has_single_cas_winner(generation_store):
    store, _ = generation_store
    workspace_id = str(uuid.uuid4())
    first, _ = _publish(store, workspace_id)

    def attempt_publish() -> str:
        try:
            return _publish(
                store,
                workspace_id,
                previous_generation_id=first.generation_id,
            )[0].generation_id
        except IndexStoreError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt_publish(), range(2)))

    assert outcomes.count("INDEX_GENERATION_CAS_MISMATCH") == 1
    winners = [value for value in outcomes if value != "INDEX_GENERATION_CAS_MISMATCH"]
    assert len(winners) == 1
    assert store.current_generation_id() == winners[0]

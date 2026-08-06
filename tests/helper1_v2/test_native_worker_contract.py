from __future__ import annotations

import hashlib
import os
import subprocess

from butler_pc_core.helper1.contracts import AssetIdentity, canonical_json, sha256_bytes
from butler_pc_core.helper1.models import NativeQwen3Generator
from butler_pc_core.helper1.security import ClosureFile, VerifiedAssetClosure


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_native_worker_protocol_receives_verified_model_fd(tmp_path):
    asset_root = tmp_path / "asset"
    asset_root.mkdir()
    model_bytes = b"GGUF-test-contract-bytes"
    (asset_root / "model.gguf").write_bytes(model_bytes)
    files = {
        "model.gguf": ClosureFile(
            path="model.gguf",
            bytes=len(model_bytes),
            sha256=sha256_bytes(model_bytes),
        )
    }
    closure_digest = sha256_bytes(
        canonical_json(
            {
                "schema_version": "butler.asset-closure.v1",
                "files": {
                    "model.gguf": {
                        "bytes": len(model_bytes),
                        "sha256": sha256_bytes(model_bytes),
                    }
                },
            }
        )
    )
    root_fd = os.open(asset_root, os.O_RDONLY | os.O_DIRECTORY)
    closure = VerifiedAssetClosure(root_fd, files, closure_digest)
    closure.verify_all()

    source = tmp_path / "worker.c"
    runner = tmp_path / "worker"
    source.write_text(
        r"""
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char request[8192] = {0};
    char model[64] = {0};
    char identity[65] = {0};
    const char *fd_marker = "\"model_fd\":";
    const char *id_marker = "\"model_identity_sha256\":\"";
    if (argc != 3 || strcmp(argv[1], "--protocol") != 0 ||
        strcmp(argv[2], "helper1-v1") != 0) return 2;
    ssize_t count = read(STDIN_FILENO, request, sizeof(request) - 1);
    if (count <= 0) return 3;
    char *fd_at = strstr(request, fd_marker);
    char *id_at = strstr(request, id_marker);
    if (fd_at == NULL || id_at == NULL) return 4;
    int model_fd = atoi(fd_at + strlen(fd_marker));
    if (lseek(model_fd, 0, SEEK_SET) < 0) return 5;
    ssize_t model_count = read(model_fd, model, sizeof(model));
    if (model_count != 24 ||
        memcmp(model, "GGUF-test-contract-bytes", 24) != 0) return 6;
    id_at += strlen(id_marker);
    memcpy(identity, id_at, 64);
    for (int index = 0; index < 64; index++) {
        if (!isxdigit((unsigned char) identity[index])) return 7;
    }
    printf(
        "{\"schema_version\":\"butler.helper1.native-response.v1\","
        "\"answer\":\"\\ud68c\\uc0ac \\uaddc\\uc815\","
        "\"claims\":[{\"claim_id\":\"claim:one\","
        "\"text\":\"\\ud68c\\uc0ac \\uaddc\\uc815\","
        "\"chunk_id\":\"chk:one\",\"evidence_start\":0,\"evidence_end\":5}],"
        "\"model_identity_sha256\":\"%s\","
        "\"loader\":\"llama_model_load_from_file_ptr\","
        "\"thinking\":false,\"kv_disposed\":true}",
        identity
    );
    return 0;
}
""",
        encoding="utf-8",
    )
    built = subprocess.run(
        ["/usr/bin/clang", "-O2", str(source), "-o", str(runner)],
        capture_output=True,
        check=False,
    )
    assert built.returncode == 0
    runner_digest = sha256_bytes(runner.read_bytes())
    identity = AssetIdentity(
        role="helper1_answer",
        model_id="Qwen/Qwen3-4B",
        upstream_revision="5617a9f61b028005a4858fdac845db406aefb181",
        closure_manifest_sha256=closure_digest,
        runtime_name="llama.cpp",
        runtime_version="pinned-test-contract",
        runtime_binary_sha256=runner_digest,
        tokenizer_sha256=_digest("tokenizer"),
    )
    generator = NativeQwen3Generator(
        model_closure=closure,
        model_relative_path="model.gguf",
        asset_identity=identity,
        runner_path=str(runner),
        chat_template_sha256=_digest("chat-template"),
        timeout_seconds=5,
    )
    try:
        result = generator.generate("bounded prompt")
    finally:
        os.close(root_fd)
    assert result.answer == "회사 규정"
    assert result.claims[0].chunk_id == "chk:one"

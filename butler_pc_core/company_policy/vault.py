from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .contracts import sha256_bytes, stable_json


class VaultError(RuntimeError):
    pass


class LocalEncryptedVault:
    """Device-local encrypted JSON vault.

    Stores encrypted bytes only. The plaintext template/policy body is returned
    only to the caller's runtime memory and is never logged by this class.
    """

    def __init__(self, root: Path | None = None, key_path: Path | None = None) -> None:
        self.root = root or Path(os.environ.get("BUTLER_POLICY_FORMAT_VAULT_DIR", str(Path.home() / ".butler" / "policy_format_vault")))
        self.key_path = key_path or Path(os.environ.get("BUTLER_POLICY_FORMAT_VAULT_KEY", str(Path.home() / ".butler" / "policy_format_vault.key")))
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_key(self) -> bytes:
        if self.key_path.exists():
            key = base64.urlsafe_b64decode(self.key_path.read_bytes())
            if len(key) != 32:
                raise VaultError("VAULT_KEY_INVALID")
            return key
        key = AESGCM.generate_key(bit_length=256)
        self.key_path.write_bytes(base64.urlsafe_b64encode(key))
        self.key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return key

    def encrypt_json(self, namespace: str, item_id: str, value: dict[str, Any], aad: str = "") -> tuple[str, str]:
        plaintext = stable_json(value).encode("utf-8")
        key = self._load_key()
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad.encode("utf-8"))
        digest = sha256_bytes(plaintext)
        envelope = {
            "schema_version": "butler.local_vault.aesgcm.v1",
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "plaintext_digest": digest,
            "aad_digest": sha256_bytes(aad.encode("utf-8")),
        }
        path = self.root / namespace
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        item_path = path / f"{item_id}.json"
        item_path.write_text(json.dumps(envelope, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        item_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return f"local-vault://{namespace}/{item_id}", digest

    def decrypt_json(self, vault_ref: str, aad: str = "") -> dict[str, Any]:
        prefix = "local-vault://"
        if not vault_ref.startswith(prefix):
            raise VaultError("VAULT_REF_INVALID")
        rel = vault_ref[len(prefix):]
        if ".." in rel or rel.startswith("/"):
            raise VaultError("VAULT_REF_TRAVERSAL_BLOCKED")
        item_path = self.root / f"{rel}.json"
        if not item_path.exists():
            raise VaultError("VAULT_ITEM_MISSING")
        envelope = json.loads(item_path.read_text(encoding="utf-8"))
        key = self._load_key()
        nonce = base64.b64decode(envelope["nonce_b64"])
        ciphertext = base64.b64decode(envelope["ciphertext_b64"])
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad.encode("utf-8"))
        if sha256_bytes(plaintext) != envelope.get("plaintext_digest"):
            raise VaultError("VAULT_DIGEST_MISMATCH")
        value = json.loads(plaintext.decode("utf-8"))
        if not isinstance(value, dict):
            raise VaultError("VAULT_VALUE_NOT_OBJECT")
        return value

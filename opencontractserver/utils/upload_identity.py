"""Stable worker-upload payload identity shared with the standalone CLI."""

import hashlib
import json


def upload_payload_digest(source_sha256: str, metadata: dict) -> str:
    payload = json.dumps(
        [source_sha256, metadata],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

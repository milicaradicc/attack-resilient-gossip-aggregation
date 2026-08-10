from __future__ import annotations

import hashlib


def bucket_of(identity: str, num_buckets: int) -> int:
    digest = hashlib.sha256(identity.encode()).digest()
    return int.from_bytes(digest, "big") % num_buckets

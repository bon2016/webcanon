"""Hashing helpers for the Retrieval Bill of Materials."""

from __future__ import annotations

import hashlib


def sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

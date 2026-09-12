"""Immutable, content-addressed artifacts; publication follows durable bytes."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from kdrx.security import has_symlink_component


class BlobStore:
    def __init__(self, root: Path):
        self.root = root.absolute()
        if has_symlink_component(root):
            raise ValueError("blob root cannot traverse links")

    def path(self, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid blob hash")
        path = self.root / digest[:2] / digest
        if has_symlink_component(path):
            raise ValueError("blob cannot traverse links")
        return path

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self.path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if self.get(digest) != data:
                raise ValueError("blob collision or corruption")
            return digest
        temp = path.with_name(".pending-" + uuid.uuid4().hex)
        try:
            with temp.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return digest

    def get(self, digest: str) -> bytes:
        data = self.path(digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("blob integrity hash mismatch")
        return data

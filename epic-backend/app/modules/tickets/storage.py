"""
AttachmentStorage abstraction. v1 implementation: local filesystem under ATTACHMENT_DIR.
A future swap to SMB share / S3 / Azure Blob is a drop-in.
"""
import os, uuid
from abc import ABC, abstractmethod
from ...config import get_settings


class AttachmentStorage(ABC):
    @abstractmethod
    def save(self, ticket_id: str, file_name: str, data: bytes) -> str: ...
    @abstractmethod
    def open(self, storage_uri: str): ...


class LocalDiskStorage(AttachmentStorage):
    def __init__(self):
        self.root = get_settings().ATTACHMENT_DIR
        os.makedirs(self.root, exist_ok=True)

    def save(self, ticket_id, file_name, data) -> str:
        safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file_name)}"
        dir_ = os.path.join(self.root, ticket_id)
        os.makedirs(dir_, exist_ok=True)
        full = os.path.join(dir_, safe_name)
        with open(full, "wb") as f:
            f.write(data)
        # Returned URI is opaque from the DB's point of view.
        return f"local://{ticket_id}/{safe_name}"

    def open(self, storage_uri: str):
        assert storage_uri.startswith("local://")
        rel = storage_uri[len("local://"):]
        full = os.path.join(self.root, rel)
        return open(full, "rb")


def get_storage() -> AttachmentStorage:
    return LocalDiskStorage()

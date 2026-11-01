"""Immutable publication must not overwrite a concurrently created destination."""

import pytest

from recycleguard.storage import BlobIntegrityError, BlobStore


def test_competing_blob_publication_never_replaces_existing_bytes(tmp_path, monkeypatch):
    store = BlobStore(tmp_path)

    def competing_link(source, destination):
        destination.write_bytes(b"competing corrupt bytes")
        raise FileExistsError(str(destination))

    monkeypatch.setattr("recycleguard.storage.blob_store.os.link", competing_link)
    with pytest.raises(BlobIntegrityError):
        store.put(b"original intended bytes", "text/plain")
    objects = list(store.objects.glob("*/*"))
    assert len(objects) == 1
    assert objects[0].read_bytes() == b"competing corrupt bytes"


def test_publication_permission_failure_is_not_silently_replaced(tmp_path, monkeypatch):
    store = BlobStore(tmp_path)

    def denied_link(source, destination):
        raise PermissionError("publication denied")

    monkeypatch.setattr("recycleguard.storage.blob_store.os.link", denied_link)
    with pytest.raises(PermissionError, match="publication denied"):
        store.put(b"original intended bytes", "text/plain")
    assert not list(store.objects.glob("*/*"))

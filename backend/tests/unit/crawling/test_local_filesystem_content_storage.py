"""Unit tests for `infrastructure/local_filesystem_content_storage.py`."""

import hashlib
from pathlib import Path

import pytest

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.exceptions import StorageIntegrityError, UnsafeStoragePathError
from app.modules.crawling.infrastructure.local_filesystem_content_storage import (
    LocalFilesystemContentStorage,
)


def _storage(tmp_path: Path) -> LocalFilesystemContentStorage:
    config = CrawlConfig(content_storage_base_dir=str(tmp_path))
    return LocalFilesystemContentStorage(config)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestSafePathConstruction:
    async def test_valid_ids_store_successfully(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"<html>hello</html>"

        reference = await storage.store_raw_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=content,
            expected_sha256=_sha256(content),
        )

        assert reference.kind == "raw"
        loaded = await storage.load_content(reference)
        assert loaded == content


class TestPathTraversalRejected:
    @pytest.mark.parametrize(
        "bad_value",
        ["../escape", "/absolute/path", "a/b", "a\x00b", "..", "a..b/../c"],
    )
    async def test_traversal_attempts_rejected(self, tmp_path: Path, bad_value: str) -> None:
        storage = _storage(tmp_path)
        content = b"data"

        with pytest.raises(UnsafeStoragePathError):
            await storage.store_raw_content(
                company_id=bad_value,
                crawl_run_id="run-1",
                page_id="page-1",
                content=content,
                expected_sha256=_sha256(content),
            )

    async def test_no_file_written_outside_base_directory(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"data"

        with pytest.raises(UnsafeStoragePathError):
            await storage.store_raw_content(
                company_id="../../escape",
                crawl_run_id="run-1",
                page_id="page-1",
                content=content,
                expected_sha256=_sha256(content),
            )

        # Nothing was written anywhere under (or outside) the base dir.
        assert list(tmp_path.rglob("*")) == []


class TestAtomicWriteAndHashVerification:
    async def test_load_content_matches_stored_hash(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"some page content" * 100

        reference = await storage.store_raw_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=content,
            expected_sha256=_sha256(content),
        )
        loaded = await storage.load_content(reference)

        assert hashlib.sha256(loaded).hexdigest() == _sha256(content)

    async def test_no_temp_files_left_behind_after_a_successful_write(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"content"

        await storage.store_raw_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=content,
            expected_sha256=_sha256(content),
        )

        written_files = list(tmp_path.rglob("*"))
        assert all(not f.name.startswith(".tmp-") for f in written_files if f.is_file())

    async def test_hash_mismatch_raises_storage_integrity_error(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"content"

        with pytest.raises(StorageIntegrityError):
            await storage.store_raw_content(
                company_id="company-1",
                crawl_run_id="run-1",
                page_id="page-1",
                content=content,
                expected_sha256="0" * 64,
            )


class TestCleanedAndTextStorage:
    async def test_cleaned_html_round_trips(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        html = "<h1>hello</h1>"

        reference = await storage.store_cleaned_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=html,
            kind="cleaned",
            expected_sha256=_sha256(html.encode("utf-8")),
        )

        loaded = await storage.load_content(reference)
        assert loaded.decode("utf-8") == html

    async def test_extracted_text_round_trips(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        text = "hello world"

        reference = await storage.store_cleaned_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=text,
            kind="text",
            expected_sha256=_sha256(text.encode("utf-8")),
        )

        loaded = await storage.load_content(reference)
        assert loaded.decode("utf-8") == text


class TestOpaqueReferences:
    async def test_reference_never_contains_a_filesystem_path(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"data"

        reference = await storage.store_raw_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=content,
            expected_sha256=_sha256(content),
        )

        assert str(tmp_path) not in reference.reference_id


class TestDeleteContent:
    async def test_delete_removes_the_stored_file(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        content = b"data"

        reference = await storage.store_raw_content(
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            content=content,
            expected_sha256=_sha256(content),
        )
        await storage.delete_content(reference)

        with pytest.raises(StorageIntegrityError):
            await storage.load_content(reference)

    async def test_delete_of_missing_content_does_not_raise(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        from app.modules.crawling.domain.models import ContentReference

        reference = ContentReference(
            reference_id="missing",
            company_id="company-1",
            crawl_run_id="run-1",
            page_id="page-1",
            kind="raw",
        )
        await storage.delete_content(reference)

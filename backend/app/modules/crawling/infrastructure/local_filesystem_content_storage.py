"""The real `ContentStorage` adapter — local filesystem, for development.

Path layout: `{base_dir}/{company_id}/{crawl_run_id}/{page_id}/
{raw.html|cleaned.html|text.txt}`. `company_id`/`crawl_run_id`/`page_id`
are always server-generated UUIDs, never user input — but every segment
is still validated against a strict allowlist pattern as defense-in-
depth, per the task's explicit "no user-controlled path traversal"
requirement. Writes are atomic (temp file in the same directory,
`os.replace()` into place) and re-verified against the caller-supplied
SHA-256 after writing. This file never returns or logs a raw filesystem
path to any caller — only opaque `ContentReference`s.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.content_storage import ContentStorage, NonRawContentKind
from app.modules.crawling.domain.exceptions import StorageIntegrityError, UnsafeStoragePathError
from app.modules.crawling.domain.models import ContentReference

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

_FILENAME_BY_KIND: dict[str, str] = {
    "raw": "raw.html",
    "cleaned": "cleaned.html",
    "text": "text.txt",
}


def _validate_id(value: str, *, field_name: str) -> str:
    if not _SAFE_ID_PATTERN.match(value):
        raise UnsafeStoragePathError(
            f"unsafe {field_name} for content storage: {value!r} "
            f"(must match {_SAFE_ID_PATTERN.pattern!r})"
        )
    return value


class LocalFilesystemContentStorage(ContentStorage):
    def __init__(self, config: CrawlConfig | None = None) -> None:
        self._base_dir = Path((config or CrawlConfig()).content_storage_base_dir)

    async def store_raw_content(
        self,
        *,
        company_id: str,
        crawl_run_id: str,
        page_id: str,
        content: bytes,
        expected_sha256: str,
    ) -> ContentReference:
        return self._store(
            company_id=company_id,
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            data=content,
            kind="raw",
            expected_sha256=expected_sha256,
        )

    async def store_cleaned_content(
        self,
        *,
        company_id: str,
        crawl_run_id: str,
        page_id: str,
        content: str,
        kind: NonRawContentKind,
        expected_sha256: str,
    ) -> ContentReference:
        return self._store(
            company_id=company_id,
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            data=content.encode("utf-8"),
            kind=kind,
            expected_sha256=expected_sha256,
        )

    async def load_content(self, reference: ContentReference) -> bytes:
        path = self._resolve_path(
            company_id=reference.company_id,
            crawl_run_id=reference.crawl_run_id,
            page_id=reference.page_id,
            kind=reference.kind,
        )
        try:
            return path.read_bytes()
        except FileNotFoundError as error:
            raise StorageIntegrityError(
                f"no stored content for reference_id={reference.reference_id!r}"
            ) from error

    async def delete_content(self, reference: ContentReference) -> None:
        path = self._resolve_path(
            company_id=reference.company_id,
            crawl_run_id=reference.crawl_run_id,
            page_id=reference.page_id,
            kind=reference.kind,
        )
        path.unlink(missing_ok=True)

    def _resolve_path(
        self,
        *,
        company_id: str,
        crawl_run_id: str,
        page_id: str,
        kind: Literal["raw", "cleaned", "text"],
    ) -> Path:
        safe_company_id = _validate_id(company_id, field_name="company_id")
        safe_crawl_run_id = _validate_id(crawl_run_id, field_name="crawl_run_id")
        safe_page_id = _validate_id(page_id, field_name="page_id")
        directory = self._base_dir / safe_company_id / safe_crawl_run_id / safe_page_id
        return directory / _FILENAME_BY_KIND[kind]

    def _store(
        self,
        *,
        company_id: str,
        crawl_run_id: str,
        page_id: str,
        data: bytes,
        kind: Literal["raw", "cleaned", "text"],
        expected_sha256: str,
    ) -> ContentReference:
        path = self._resolve_path(
            company_id=company_id, crawl_run_id=crawl_run_id, page_id=page_id, kind=kind
        )
        self._atomic_write(path, data)
        self._verify_hash(path, expected_sha256=expected_sha256)

        return ContentReference(
            reference_id=f"{company_id}:{crawl_run_id}:{page_id}:{kind}",
            company_id=company_id,
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            kind=kind,
        )

    def _atomic_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def _verify_hash(self, path: Path, *, expected_sha256: str) -> None:
        written = path.read_bytes()
        actual_sha256 = hashlib.sha256(written).hexdigest()
        if actual_sha256 != expected_sha256:
            raise StorageIntegrityError(
                f"content hash mismatch after write: expected {expected_sha256!r}, "
                f"got {actual_sha256!r}"
            )

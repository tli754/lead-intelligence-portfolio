"""Port for storing/loading page content externally to MongoDB.

Pure abstract contract — no filesystem/S3/Motor import here (those are
confined to `infrastructure/`). The crawl service never depends directly
on local disk or S3, only on this interface, operating exclusively on
opaque `ContentReference`s — never a raw path string in either direction.

**Why `store_cleaned_content` takes a `kind`, not a separate `store_text`
method:** the task brief's own literal method list (section 11) has only
`store_raw_content`/`store_cleaned_content`/`load_content`/
`delete_content` — four methods — even though three distinct artifacts
(raw HTML, cleaned HTML, extracted text) may need external storage
(`ContentStorageInfo` in `domain/models.py` has both a
`cleaned_html_reference` and an `extracted_text_reference`). Resolved by
having `store_cleaned_content` accept a `kind: Literal["cleaned", "text"]`
so one method serves both non-raw artifacts, matching the brief's literal
method count while still covering all three.
"""

from abc import ABC, abstractmethod
from typing import Literal

from app.modules.crawling.domain.models import ContentReference

NonRawContentKind = Literal["cleaned", "text"]


class ContentStorage(ABC):
    @abstractmethod
    async def store_raw_content(
        self,
        *,
        company_id: str,
        crawl_run_id: str,
        page_id: str,
        content: bytes,
        expected_sha256: str,
    ) -> ContentReference:
        """Stores raw fetched bytes. Raises `UnsafeStoragePathError` for
        an unsafe id, `StorageIntegrityError` if the written content's
        hash doesn't match `expected_sha256`."""
        ...

    @abstractmethod
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
        """Stores cleaned HTML (`kind="cleaned"`) or extracted text
        (`kind="text"`) — only called when the artifact is above its
        configured inline-storage threshold."""
        ...

    @abstractmethod
    async def load_content(self, reference: ContentReference) -> bytes:
        """Re-derives and re-validates the storage path from `reference`'s
        fields on every call — never trusts a cached path."""
        ...

    @abstractmethod
    async def delete_content(self, reference: ContentReference) -> None: ...

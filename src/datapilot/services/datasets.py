"""Safe, streaming dataset ingestion."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import AsyncIterable
from pathlib import Path
from uuid import uuid4

import anyio
from sqlalchemy.exc import IntegrityError

from datapilot.domain import DatasetIngestResult
from datapilot.persistence import DatasetRepository
from datapilot.security import PathSecurityError, resolve_under_root, validate_client_filename

MEDIA_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".sqlite": "application/vnd.sqlite3",
    ".db": "application/vnd.sqlite3",
}


class DatasetValidationError(ValueError):
    """Raised when upload metadata or content violates the ingestion contract."""


class UploadTooLargeError(DatasetValidationError):
    """Raised as soon as a streamed upload exceeds the configured byte limit."""


class EmptyDatasetError(DatasetValidationError):
    """Raised when the upload contains no bytes."""


class DatasetService:
    """Validate, hash, deduplicate, and atomically store uploaded datasets."""

    def __init__(
        self,
        repository: DatasetRepository,
        *,
        data_root: Path,
        max_upload_bytes: int,
    ) -> None:
        if max_upload_bytes < 1:
            raise ValueError("max_upload_bytes must be positive")
        self.repository = repository
        self.data_root = data_root.resolve()
        self.max_upload_bytes = max_upload_bytes

    async def ingest(
        self,
        *,
        filename: str,
        chunks: AsyncIterable[bytes],
    ) -> DatasetIngestResult:
        try:
            safe_filename = validate_client_filename(filename)
        except PathSecurityError as error:
            raise DatasetValidationError(str(error)) from error

        suffix = Path(safe_filename).suffix.lower()
        media_type = MEDIA_TYPES.get(suffix)
        if media_type is None:
            allowed = ", ".join(sorted(MEDIA_TYPES))
            raise DatasetValidationError(f"unsupported dataset type; allowed: {allowed}")

        uploads_root = resolve_under_root(self.data_root, "uploads")
        uploads_root.mkdir(parents=True, exist_ok=True)
        dataset_id = f"ds_{uuid4().hex}"
        dataset_dir = resolve_under_root(uploads_root, dataset_id)
        dataset_dir.mkdir()
        temporary_path = resolve_under_root(dataset_dir, ".uploading")
        final_path = resolve_under_root(dataset_dir, f"source{suffix}")

        digest = hashlib.sha256()
        size = 0
        try:
            async with await anyio.open_file(temporary_path, "wb") as output:
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise DatasetValidationError("upload chunks must be bytes")
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise UploadTooLargeError(
                            f"upload exceeds the {self.max_upload_bytes}-byte limit"
                        )
                    digest.update(chunk)
                    await output.write(chunk)

            if size == 0:
                raise EmptyDatasetError("dataset cannot be empty")

            sha256 = digest.hexdigest()
            existing = await self.repository.get_by_sha256(sha256)
            if existing is not None:
                self._remove_upload_dir(dataset_dir, uploads_root)
                return DatasetIngestResult(dataset=existing, deduplicated=True)

            os.replace(temporary_path, final_path)
            stored_path = final_path.relative_to(self.data_root).as_posix()
            try:
                dataset = await self.repository.create(
                    dataset_id=dataset_id,
                    original_name=safe_filename,
                    stored_path=stored_path,
                    sha256=sha256,
                    media_type=media_type,
                    size=size,
                )
            except IntegrityError:
                # A concurrent request may have inserted the same digest after our lookup.
                existing = await self.repository.get_by_sha256(sha256)
                if existing is None:
                    raise
                self._remove_upload_dir(dataset_dir, uploads_root)
                return DatasetIngestResult(dataset=existing, deduplicated=True)
            return DatasetIngestResult(dataset=dataset)
        except Exception:
            self._remove_upload_dir(dataset_dir, uploads_root)
            raise

    @staticmethod
    def _remove_upload_dir(dataset_dir: Path, uploads_root: Path) -> None:
        """Remove only the generated per-upload directory after revalidating scope."""

        safe_directory = resolve_under_root(uploads_root, dataset_dir)
        if safe_directory != uploads_root and safe_directory.exists():
            shutil.rmtree(safe_directory)

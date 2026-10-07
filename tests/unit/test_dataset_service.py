from collections.abc import AsyncIterator
from hashlib import sha256
from pathlib import Path

import pytest

from datapilot.persistence import Database, DatasetRepository
from datapilot.services import (
    DatasetService,
    DatasetValidationError,
    EmptyDatasetError,
    UploadTooLargeError,
)


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.initialize()
    yield database
    await database.dispose()


async def byte_chunks(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def make_service(database: Database, tmp_path: Path, *, limit: int = 1024) -> DatasetService:
    return DatasetService(
        DatasetRepository(database),
        data_root=tmp_path,
        max_upload_bytes=limit,
    )


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("sales.csv", "text/csv"),
        (
            "sales.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("sales.sqlite", "application/vnd.sqlite3"),
        ("sales.db", "application/vnd.sqlite3"),
    ],
)
async def test_allowed_extensions_use_expected_media_type(
    database: Database,
    tmp_path: Path,
    filename: str,
    media_type: str,
) -> None:
    service = make_service(database, tmp_path)

    result = await service.ingest(filename=filename, chunks=byte_chunks(filename.encode()))

    assert result.dataset.media_type == media_type


async def test_ingest_streams_hashes_and_uses_relative_path(
    database: Database,
    tmp_path: Path,
) -> None:
    service = make_service(database, tmp_path)
    content = b"region,revenue\nEast,120\nWest,150\n"

    result = await service.ingest(
        filename="sales.CSV",
        chunks=byte_chunks(content[:10], content[10:]),
    )

    stored_file = tmp_path / result.dataset.stored_path
    assert result.deduplicated is False
    assert result.dataset.original_name == "sales.CSV"
    assert result.dataset.media_type == "text/csv"
    assert result.dataset.size == len(content)
    assert result.dataset.sha256 == sha256(content).hexdigest()
    assert not Path(result.dataset.stored_path).is_absolute()
    assert stored_file.read_bytes() == content
    assert not (stored_file.parent / ".uploading").exists()


async def test_duplicate_content_reuses_record_and_removes_second_file(
    database: Database,
    tmp_path: Path,
) -> None:
    service = make_service(database, tmp_path)
    content = b"region,revenue\nEast,120\n"

    first = await service.ingest(filename="sales.csv", chunks=byte_chunks(content))
    second = await service.ingest(filename="copy.csv", chunks=byte_chunks(content))

    assert second.deduplicated is True
    assert second.dataset.id == first.dataset.id
    assert list((tmp_path / "uploads").glob("*/source.csv")) == [
        tmp_path / first.dataset.stored_path
    ]


async def test_oversized_upload_is_rejected_and_cleaned(
    database: Database,
    tmp_path: Path,
) -> None:
    service = make_service(database, tmp_path, limit=5)

    with pytest.raises(UploadTooLargeError, match="5-byte"):
        await service.ingest(filename="sales.csv", chunks=byte_chunks(b"123", b"456"))

    assert list((tmp_path / "uploads").iterdir()) == []


async def test_empty_upload_is_rejected_and_cleaned(
    database: Database,
    tmp_path: Path,
) -> None:
    service = make_service(database, tmp_path)

    with pytest.raises(EmptyDatasetError):
        await service.ingest(filename="sales.csv", chunks=byte_chunks(b""))

    assert list((tmp_path / "uploads").iterdir()) == []


@pytest.mark.parametrize("filename", ["../sales.csv", "sales.exe", "sales.csv.exe"])
async def test_invalid_filename_or_extension_is_rejected_before_writing(
    database: Database,
    tmp_path: Path,
    filename: str,
) -> None:
    service = make_service(database, tmp_path)

    with pytest.raises(DatasetValidationError):
        await service.ingest(filename=filename, chunks=byte_chunks(b"content"))

    assert not (tmp_path / "uploads").exists()

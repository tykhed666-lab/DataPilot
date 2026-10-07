from pathlib import Path

import pytest

from datapilot.security import PathSecurityError, resolve_under_root, validate_client_filename


def test_resolve_under_root_accepts_descendant(tmp_path: Path) -> None:
    resolved = resolve_under_root(tmp_path, "uploads/dataset/source.csv")

    assert resolved == tmp_path / "uploads" / "dataset" / "source.csv"


@pytest.mark.parametrize(
    "candidate",
    ["../outside.csv", "uploads/../../outside.csv"],
)
def test_resolve_under_root_rejects_traversal(tmp_path: Path, candidate: str) -> None:
    with pytest.raises(PathSecurityError, match="escapes"):
        resolve_under_root(tmp_path, candidate)


def test_resolve_under_root_rejects_sibling_prefix(tmp_path: Path) -> None:
    sibling = tmp_path.parent / f"{tmp_path.name}-other" / "source.csv"

    with pytest.raises(PathSecurityError, match="escapes"):
        resolve_under_root(tmp_path, sibling)


@pytest.mark.parametrize("filename", ["../sales.csv", "folder/sales.csv", "folder\\sales.csv"])
def test_validate_client_filename_rejects_paths(filename: str) -> None:
    with pytest.raises(PathSecurityError):
        validate_client_filename(filename)

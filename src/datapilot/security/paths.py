"""Path validation that keeps user-controlled names inside an approved root."""

from __future__ import annotations

from os import PathLike
from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when a path or filename crosses the storage boundary."""


def resolve_under_root(root: Path, candidate: str | PathLike[str]) -> Path:
    """Resolve *candidate* and prove it remains below *root*.

    Relative candidates are interpreted from the root. Absolute candidates are
    accepted only when they already point inside it.
    """

    resolved_root = root.resolve()
    candidate_path = Path(candidate)
    if not candidate_path.is_absolute():
        candidate_path = resolved_root / candidate_path
    resolved_candidate = candidate_path.resolve()

    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise PathSecurityError("path escapes the configured storage root") from error
    return resolved_candidate


def validate_client_filename(filename: str) -> str:
    """Accept a plain client filename, never a path supplied by the client."""

    if not filename or not filename.strip():
        raise PathSecurityError("filename cannot be empty")
    if len(filename) > 255:
        raise PathSecurityError("filename is longer than 255 characters")
    if filename in {".", ".."}:
        raise PathSecurityError("filename cannot be a relative path marker")
    if any(character in filename for character in ("/", "\\", "\0")):
        raise PathSecurityError("filename must not contain path separators")
    if any(ord(character) < 32 for character in filename):
        raise PathSecurityError("filename must not contain control characters")
    return filename

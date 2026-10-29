"""Helper for Phase 0 stub endpoints: every unbuilt endpoint answers 501 with its owner."""
from fastapi import HTTPException


def not_implemented(feature: str, owner: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=f"{feature} is not implemented yet (Phase 1, {owner}). Fill in this router; "
               f"contracts are in schemas.py and docs are in the module docstring.",
    )

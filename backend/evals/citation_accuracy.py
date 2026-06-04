from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def check_citations(
    citations: list[dict[str, Any]],
    regulatory_store: Any,
    policy_store: Any,
) -> dict[str, Any]:
    total = len(citations)
    valid = 0
    invalid: list[str] = []

    for citation in citations:
        source = citation.get("source", "")
        ids = citation.get("ids", [])

        if not ids:
            if source:
                valid += 1
            continue

        for chunk_id in ids:
            chunk_id_str = str(chunk_id)
            found = False

            if regulatory_store and hasattr(regulatory_store, "_chunks"):
                for chunk in regulatory_store._chunks:
                    if chunk.id == chunk_id_str:
                        found = True
                        break

            if not found and policy_store and hasattr(policy_store, "_collection"):
                try:
                    result = policy_store._collection.get(ids=[chunk_id_str])
                    if result and result.get("ids"):
                        found = True
                except Exception:
                    pass

            if found:
                valid += 1
            else:
                invalid.append(chunk_id_str)

    accuracy = valid / total if total > 0 else 1.0

    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "accuracy": accuracy,
    }

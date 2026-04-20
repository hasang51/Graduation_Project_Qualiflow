"""Deterministic page-selector for cost-minimized LLM requests.

Given a list of :class:`~app.services.preprocessing.ProcessedPage` objects
and a quality class string, the selector returns the subset of pages that
are most likely to contain useful extraction signal, capped by the
per-quality-class limit from :class:`~app.services.batch_policy.BatchRunPolicy`.

The selector is **fully deterministic** (no randomness, no ML inference).
It ranks pages by cheap heuristics derived from already-computed metadata:

1. Pages that are NOT blank (blur_score > 0 or text content hints).
2. Pages that have a ``table_crop_available`` flag (table presence hint).
3. Pages with the highest blur score (sharper = more readable, more signal).
4. Page 1 always included unless the document has more structure on later pages.

Selection strategy by quality class:
- ``digital_clean``: 1–2 pages (usually all content is on page 1)
- ``scan_clean``: 1–2 pages
- ``scan_degraded``: up to ``max_pages`` (default 3) but prefer pages with
  table presence
- severe_scan (blur < threshold): caller should skip entirely (see batch_policy)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.preprocessing import ProcessedPage


@dataclass
class PageSelectionResult:
    selected_indices: list[int]   # 0-based indices into the original pages list
    selected_pages: list          # the actual ProcessedPage objects
    total_pages: int
    reason: str
    pages_skipped: int


def select_pages(
    pages: list,
    *,
    quality_class: str,
    max_pages: int,
) -> PageSelectionResult:
    """Return the best ``max_pages`` pages from ``pages`` for LLM submission.

    Parameters
    ----------
    pages:
        Full list of :class:`~app.services.preprocessing.ProcessedPage`
        objects produced by ``preprocess_pdf``.
    quality_class:
        The document-level quality class string (``digital_clean``,
        ``scan_clean``, ``scan_degraded``).
    max_pages:
        Hard upper bound on returned pages.
    """

    if not pages:
        return PageSelectionResult(
            selected_indices=[],
            selected_pages=[],
            total_pages=0,
            reason="no_pages",
            pages_skipped=0,
        )

    total = len(pages)
    cap = min(max_pages, total)

    if total <= cap:
        return PageSelectionResult(
            selected_indices=list(range(total)),
            selected_pages=list(pages),
            total_pages=total,
            reason=f"all_{total}_pages_within_cap",
            pages_skipped=0,
        )

    # Score each page — higher = more useful.
    scored: list[tuple[float, int]] = []
    for i, page in enumerate(pages):
        score = _score_page(page, page_index=i)
        scored.append((score, i))

    # Ensure page 0 (first page) is always included — it almost always has
    # the document header and supplier info.
    scored.sort(key=lambda t: (-t[0], t[1]))

    selected_indices: list[int] = []
    # Always include page index 0 first.
    if any(idx == 0 for _, idx in scored):
        selected_indices.append(0)

    for score, idx in scored:
        if idx not in selected_indices:
            selected_indices.append(idx)
        if len(selected_indices) >= cap:
            break

    # Keep in document order for the model (it processes top-to-bottom).
    selected_indices.sort()
    selected = [pages[i] for i in selected_indices]
    skipped = total - len(selected_indices)

    reason = (
        f"quality={quality_class} selected={len(selected_indices)}/{total} "
        f"(cap={cap}) skipped={skipped}"
    )
    return PageSelectionResult(
        selected_indices=selected_indices,
        selected_pages=selected,
        total_pages=total,
        reason=reason,
        pages_skipped=skipped,
    )


def _score_page(page: "ProcessedPage", *, page_index: int) -> float:
    """Assign a desirability score to a page. Higher is better."""
    score = 0.0

    # Page 1 (index 0) always gets a large bonus — header/supplier data.
    if page_index == 0:
        score += 100.0

    # Table presence is a very strong signal for CoA/MTC content.
    if getattr(page, "table_crop_available", False):
        score += 80.0

    # A higher blur score means a sharper image — better for extraction.
    blur = None
    if hasattr(page, "quality_assessment") and page.quality_assessment:
        blur = getattr(page.quality_assessment, "blur_score", None)
    if blur is None:
        # Fall back to checking variant names.
        blur = _estimate_blur_from_variants(page)
    if blur is not None:
        # Normalise: 200 = clean, 20 = very blurry.
        score += min(blur / 200.0 * 20.0, 20.0)

    # Pages with selected_variants set scored higher — the preprocessing
    # strategy already found them useful.
    if getattr(page, "selected_variants", None):
        score += 10.0

    # Low page numbers are generally more information-dense in MTC docs.
    score -= page_index * 2.0

    return score


def _estimate_blur_from_variants(page: "ProcessedPage") -> float | None:
    """Try to read blur from the page's available variants metadata."""
    variants = getattr(page, "variants", {})
    if not variants:
        return None
    # We cannot cheaply read blur from an EncodedVariant without decoding.
    # Return None and let the caller use the page-index heuristic.
    return None

"""
book_service.py

PDF ingestion, OCR, deterministic cleanup, and reading-mode queries.

Pipeline per document:
  1. Save uploaded PDF to disk
  2. Open with PyMuPDF; detect total pages
  3. For each page:
       a. Try embedded text extraction (text-native path)
       b. If text is too sparse (scan heuristic) → render PNG + pytesseract OCR
       c. Run deterministic cleanup on all extracted blocks
       d. Flag header/footer blocks by position heuristic
       e. Insert book_pages + book_blocks rows
  4. Update book_documents status to 'ready' (or 'error')

Cleanup steps (no LLM):
  - Unicode NFC normalization
  - Ligature repair  (ﬁ→fi, ﬂ→fl, ﬀ→ff, ﬃ→ffi, ﬄ→ffl)
  - Zero-width char removal
  - End-of-line dehyphenation  (word-\n → word)
  - Whitespace collapse
  - Artifact filter (< 30% alpha chars → drop)
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# ── Storage paths ─────────────────────────────────────────────────────────────
_UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "uploads"))
_BOOKS_DIR   = _UPLOAD_ROOT / "books"
_PAGES_DIR   = _UPLOAD_ROOT / "pages"

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="book_proc")

# ── Scan detection threshold ──────────────────────────────────────────────────
# A page with fewer embedded characters than this is treated as scanned.
_MIN_TEXT_CHARS = 80

# ── Deterministic cleanup ─────────────────────────────────────────────────────
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")
_MULTISPACE  = re.compile(r"[ \t]+")
_MULTINEWLINE = re.compile(r"\n{3,}")
# Soft-hyphen line break: "word-\n word" → "wordword"
_SOFTHYPHEN  = re.compile(r"-\s*\n\s*")


def _clean_text(text: str) -> str:
    """Apply deterministic cleanup. Returns cleaned text (may be empty)."""
    # 1. Unicode NFC
    text = unicodedata.normalize("NFC", text)
    # 2. Ligatures
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    # 3. Zero-width / soft-hyphen chars
    text = _ZERO_WIDTH.sub("", text)
    # 4. Dehyphenate line-end hyphens
    text = _SOFTHYPHEN.sub("", text)
    # 5. Collapse runs of spaces/tabs (preserve newlines as paragraph separators)
    text = _MULTISPACE.sub(" ", text)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text.strip()


def _is_ocr_artifact(text: str) -> bool:
    """Return True if text looks like a non-textual OCR artifact."""
    if len(text) < 2:
        return True
    alpha = sum(1 for c in text if c.isalpha())
    return alpha / len(text) < 0.30


# ── Header/footer detection ────────────────────────────────────────────────────
_PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")


def _mark_header_footer(blocks: list[dict], page_height: float) -> None:
    """
    Mutate blocks in-place: set is_header_footer=True for blocks in the top/bottom
    8% margin zone, or blocks that look like bare page numbers.
    """
    top_thresh = page_height * 0.08
    bot_thresh = page_height * 0.92
    for block in blocks:
        y0, y1 = block["bbox_y0"], block["bbox_y1"]
        text = block["clean_text"] or ""
        in_margin = (y1 < top_thresh) or (y0 > bot_thresh)
        is_page_num = bool(_PAGE_NUM_RE.match(text))
        block["is_header_footer"] = in_margin or is_page_num


# ── Text-native extraction ────────────────────────────────────────────────────

def _extract_native_blocks(page) -> list[dict]:
    """
    Extract text blocks from a fitz page using embedded PDF text.
    Returns a list of block dicts ready for DB insertion.
    """
    raw_blocks = page.get_text("blocks")
    result = []
    for b in raw_blocks:
        x0, y0, x1, y1, text, block_no, block_type = b
        if block_type != 0:          # 0 = text block; 1 = image block
            continue
        cleaned = _clean_text(text)
        if not cleaned or _is_ocr_artifact(cleaned):
            continue
        result.append({
            "block_index": block_no,
            "bbox_x0": float(x0), "bbox_y0": float(y0),
            "bbox_x1": float(x1), "bbox_y1": float(y1),
            "ocr_text": text,
            "clean_text": cleaned,
            "ocr_confidence": None,  # not applicable for text-native
            "is_header_footer": False,
        })
    return result


# ── OCR extraction ────────────────────────────────────────────────────────────

def _render_page_to_png(page, dpi: int = 200) -> bytes:
    """Render a fitz page to a PNG byte string at the given DPI."""
    import fitz  # PyMuPDF (lazy import — not mandatory if OCR path never used)
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def _ocr_page_png(png_bytes: bytes, dpi: int, page_w_pt: float, page_h_pt: float) -> list[dict]:
    """
    Run pytesseract on a rendered page image.
    Returns block dicts grouped by Tesseract's block_num.
    Coordinates are converted from pixels back to PDF points.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        logger.warning("pytesseract or Pillow not installed; OCR skipped")
        return []

    img = Image.open(io.BytesIO(png_bytes))
    scale = 72.0 / dpi  # pixel → pt

    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        logger.error("pytesseract failed: %s", exc)
        return []

    # Accumulate words into block-level groups
    groups: dict[int, dict] = {}
    for i in range(len(data["text"])):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        conf_raw = data["conf"][i]
        conf = float(conf_raw) / 100.0 if str(conf_raw) != "-1" else 0.0
        bn = data["block_num"][i]
        px_left  = data["left"][i]
        px_top   = data["top"][i]
        px_right = px_left + data["width"][i]
        px_bot   = px_top  + data["height"][i]
        if bn not in groups:
            groups[bn] = {"words": [], "confs": [],
                          "px_x0": px_left, "px_y0": px_top,
                          "px_x1": px_right, "px_y1": px_bot}
        else:
            g = groups[bn]
            g["px_x0"] = min(g["px_x0"], px_left)
            g["px_y0"] = min(g["px_y0"], px_top)
            g["px_x1"] = max(g["px_x1"], px_right)
            g["px_y1"] = max(g["px_y1"], px_bot)
        groups[bn]["words"].append(word)
        groups[bn]["confs"].append(conf)

    result = []
    for idx, (bn, g) in enumerate(sorted(groups.items())):
        raw_text = " ".join(g["words"])
        cleaned  = _clean_text(raw_text)
        if not cleaned or _is_ocr_artifact(cleaned):
            continue
        avg_conf = sum(g["confs"]) / len(g["confs"]) if g["confs"] else 0.0
        result.append({
            "block_index": idx,
            "bbox_x0": round(g["px_x0"] * scale, 2),
            "bbox_y0": round(g["px_y0"] * scale, 2),
            "bbox_x1": round(g["px_x1"] * scale, 2),
            "bbox_y1": round(g["px_y1"] * scale, 2),
            "ocr_text":        raw_text,
            "clean_text":      cleaned,
            "ocr_confidence":  round(avg_conf, 3),
            "is_header_footer": False,
        })
    return result


# ── Core document processing (runs in thread pool) ───────────────────────────

def _process_pdf_sync(doc_id: str, pdf_path: Path, language: str) -> dict:
    """
    Synchronous PDF processing. Called via run_in_executor.
    Returns a summary dict: {total_pages, source_type, pages: [...]}
    Each page: {page_number, width_pt, height_pt, is_scanned, image_bytes?, blocks}
    """
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF (fitz) is not installed — cannot process PDFs")

    pdf_doc = fitz.open(str(pdf_path))
    total_pages = len(pdf_doc)
    pages_data  = []
    scan_count  = 0

    for page_num in range(total_pages):
        page     = pdf_doc[page_num]
        w_pt     = float(page.rect.width)
        h_pt     = float(page.rect.height)

        # Attempt embedded text extraction
        raw_char_count = len(page.get_text("text"))
        is_scanned = raw_char_count < _MIN_TEXT_CHARS

        if is_scanned:
            scan_count += 1
            png_bytes = _render_page_to_png(page, dpi=200)
            blocks    = _ocr_page_png(png_bytes, dpi=200, page_w_pt=w_pt, page_h_pt=h_pt)
        else:
            png_bytes = None
            blocks    = _extract_native_blocks(page)

        _mark_header_footer(blocks, h_pt)

        pages_data.append({
            "page_number": page_num + 1,   # 1-based
            "width_pt":    w_pt,
            "height_pt":   h_pt,
            "is_scanned":  is_scanned,
            "image_bytes": png_bytes,
            "blocks":      blocks,
        })

    pdf_doc.close()

    # Determine overall source type
    if scan_count == 0:
        source_type = "pdf_text"
    elif scan_count == total_pages:
        source_type = "pdf_scan"
    else:
        source_type = "mixed"

    return {
        "total_pages": total_pages,
        "source_type": source_type,
        "pages":       pages_data,
    }


def _save_page_image(doc_id: str, page_number: int, png_bytes: bytes) -> str:
    """Save a rendered page PNG and return the file path string."""
    page_dir = _PAGES_DIR / doc_id
    page_dir.mkdir(parents=True, exist_ok=True)
    img_path = page_dir / f"page_{page_number:04d}.png"
    img_path.write_bytes(png_bytes)
    return str(img_path)


# ── Async DB helpers ──────────────────────────────────────────────────────────

async def _persist_processing_results(
    pool: asyncpg.Pool,
    doc_id: str,
    result: dict,
) -> None:
    """Write pages + blocks to the DB after successful processing."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Update document header
            await conn.execute(
                """
                UPDATE book_documents
                   SET total_pages = $1,
                       source_type = $2,
                       status      = 'ready',
                       updated_at  = NOW()
                 WHERE doc_id = $3
                """,
                result["total_pages"],
                result["source_type"],
                doc_id,
            )

            for page in result["pages"]:
                pn         = page["page_number"]
                png_bytes  = page["image_bytes"]
                image_path = None

                if png_bytes:
                    image_path = _save_page_image(doc_id, pn, png_bytes)

                page_id = await conn.fetchval(
                    """
                    INSERT INTO book_pages
                        (doc_id, page_number, image_path, width_pt, height_pt, is_scanned)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING page_id
                    """,
                    doc_id,
                    pn,
                    image_path,
                    page["width_pt"],
                    page["height_pt"],
                    page["is_scanned"],
                )

                if page["blocks"]:
                    await conn.executemany(
                        """
                        INSERT INTO book_blocks
                            (page_id, doc_id, block_index, block_type,
                             bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                             ocr_text, clean_text, ocr_confidence, is_header_footer)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                        """,
                        [
                            (
                                page_id, doc_id, b["block_index"], "text",
                                b["bbox_x0"], b["bbox_y0"], b["bbox_x1"], b["bbox_y1"],
                                b["ocr_text"], b["clean_text"], b["ocr_confidence"],
                                b["is_header_footer"],
                            )
                            for b in page["blocks"]
                        ],
                    )


async def _mark_error(pool: asyncpg.Pool, doc_id: str, message: str) -> None:
    await pool.execute(
        """
        UPDATE book_documents
           SET status = 'error', error_message = $1, updated_at = NOW()
         WHERE doc_id = $2
        """,
        message[:2000],
        doc_id,
    )


# ── Background processing task ────────────────────────────────────────────────

async def process_document(pool: asyncpg.Pool, doc_id: str, pdf_path: Path, language: str) -> None:
    """
    Entry point for background processing. Runs CPU-bound work in executor,
    then persists results to DB asynchronously.
    """
    import asyncio

    # Mark processing
    await pool.execute(
        "UPDATE book_documents SET status='processing', updated_at=NOW() WHERE doc_id=$1",
        doc_id,
    )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            _process_pdf_sync,
            doc_id, pdf_path, language,
        )
    except Exception as exc:
        logger.error("PDF processing failed for %s: %s", doc_id, exc, exc_info=True)
        await _mark_error(pool, doc_id, str(exc))
        return

    try:
        await _persist_processing_results(pool, doc_id, result)
    except Exception as exc:
        logger.error("DB persistence failed for %s: %s", doc_id, exc, exc_info=True)
        await _mark_error(pool, doc_id, f"DB write failed: {exc}")


# ── Book CRUD ─────────────────────────────────────────────────────────────────

async def create_document(
    pool: asyncpg.Pool,
    user_id: str,
    title: str,
    filename: str,
    language: str,
    file_bytes: bytes,
) -> str:
    """
    Save the uploaded PDF and create the DB record.
    Returns the new doc_id (UUID string).
    """
    doc_id = str(uuid.uuid4())
    _BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _BOOKS_DIR / f"{doc_id}.pdf"
    pdf_path.write_bytes(file_bytes)

    await pool.execute(
        """
        INSERT INTO book_documents
            (doc_id, user_id, title, filename, file_path, language)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        doc_id, user_id, title, filename, str(pdf_path), language,
    )
    return doc_id


async def list_documents(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT doc_id, user_id, title, filename, total_pages, language,
               source_type, status, error_message, created_at, updated_at
          FROM book_documents
         WHERE user_id = $1
         ORDER BY created_at DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def get_document(pool: asyncpg.Pool, doc_id: str, user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT doc_id, user_id, title, filename, total_pages, language,
               source_type, status, error_message, created_at, updated_at
          FROM book_documents
         WHERE doc_id = $1 AND user_id = $2
        """,
        doc_id, user_id,
    )
    return dict(row) if row else None


async def list_pages(pool: asyncpg.Pool, doc_id: str) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT p.page_id, p.page_number, p.is_scanned, p.image_path,
               COUNT(b.block_id) AS block_count
          FROM book_pages p
          LEFT JOIN book_blocks b ON b.page_id = p.page_id
         WHERE p.doc_id = $1
         GROUP BY p.page_id
         ORDER BY p.page_number
        """,
        doc_id,
    )
    return [
        {
            "page_id":     r["page_id"],
            "page_number": r["page_number"],
            "is_scanned":  r["is_scanned"],
            "has_image":   r["image_path"] is not None,
            "block_count": r["block_count"],
        }
        for r in rows
    ]


async def get_page_detail(pool: asyncpg.Pool, doc_id: str, page_number: int) -> dict | None:
    page_row = await pool.fetchrow(
        """
        SELECT page_id, page_number, is_scanned, image_path, width_pt, height_pt
          FROM book_pages
         WHERE doc_id = $1 AND page_number = $2
        """,
        doc_id, page_number,
    )
    if not page_row:
        return None

    blocks_rows = await pool.fetch(
        """
        SELECT block_id, block_index, block_type,
               bbox_x0, bbox_y0, bbox_x1, bbox_y1,
               ocr_text, clean_text, corrected_text,
               correction_status, ocr_confidence, is_header_footer,
               user_text_override
          FROM book_blocks
         WHERE page_id = $1
         ORDER BY block_index
        """,
        page_row["page_id"],
    )

    blocks = []
    for b in blocks_rows:
        display_text = _resolve_display_text(
            user_text_override=b["user_text_override"],
            correction_status=b["correction_status"],
            corrected_text=b["corrected_text"],
            clean_text=b["clean_text"],
        )
        blocks.append({
            **dict(b),
            "display_text": display_text,
        })

    return {
        "page_id":    page_row["page_id"],
        "page_number": page_row["page_number"],
        "is_scanned": page_row["is_scanned"],
        "has_image":  page_row["image_path"] is not None,
        "width_pt":   page_row["width_pt"],
        "height_pt":  page_row["height_pt"],
        "blocks":     blocks,
    }


def _resolve_display_text(
    user_text_override: str | None,
    correction_status: str,
    corrected_text: str | None,
    clean_text: str | None,
) -> str:
    """Priority chain: user override > approved correction > clean_text > ''."""
    if user_text_override is not None:
        return user_text_override
    if correction_status == "approved" and corrected_text:
        return corrected_text
    return clean_text or ""


async def get_page_image_path(pool: asyncpg.Pool, doc_id: str, page_number: int) -> str | None:
    row = await pool.fetchrow(
        "SELECT image_path FROM book_pages WHERE doc_id=$1 AND page_number=$2",
        doc_id, page_number,
    )
    if not row or not row["image_path"]:
        return None
    return row["image_path"]


async def patch_block(
    pool: asyncpg.Pool,
    block_id: int,
    doc_id: str,
    block_type: str | None,
    user_text_override: str | None,
    correction_status: str | None,
) -> dict | None:
    """
    Apply a partial update to a block. Only supplied fields are changed.
    user_text_override='' clears the override.
    Returns the updated block row or None if not found.
    """
    # Build SET clause dynamically
    sets, params = [], [block_id, doc_id]

    if block_type is not None:
        params.append(block_type)
        sets.append(f"block_type = ${len(params)}")

    if user_text_override is not None:
        # Empty string means "clear override" → store NULL
        params.append(user_text_override if user_text_override else None)
        sets.append(f"user_text_override = ${len(params)}")

    if correction_status is not None:
        if correction_status not in ("approved", "rejected"):
            raise ValueError(f"Invalid correction_status: {correction_status}")
        params.append(correction_status)
        sets.append(f"correction_status = ${len(params)}")

    if not sets:
        # Nothing to update; return current state
        row = await pool.fetchrow(
            "SELECT * FROM book_blocks WHERE block_id=$1 AND doc_id=$2",
            block_id, doc_id,
        )
        return dict(row) if row else None

    query = f"""
        UPDATE book_blocks
           SET {', '.join(sets)}
         WHERE block_id = $1 AND doc_id = $2
        RETURNING *
    """
    row = await pool.fetchrow(query, *params)
    return dict(row) if row else None


async def get_block(pool: asyncpg.Pool, block_id: int, doc_id: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM book_blocks WHERE block_id=$1 AND doc_id=$2",
        block_id, doc_id,
    )
    return dict(row) if row else None


async def save_llm_correction(
    pool: asyncpg.Pool,
    block_id: int,
    doc_id: str,
    corrected_text: str,
) -> dict | None:
    """Store an LLM-suggested correction; set status to 'suggested'."""
    row = await pool.fetchrow(
        """
        UPDATE book_blocks
           SET corrected_text    = $1,
               correction_status = 'suggested'
         WHERE block_id = $2 AND doc_id = $3
        RETURNING *
        """,
        corrected_text, block_id, doc_id,
    )
    return dict(row) if row else None


async def list_low_confidence_blocks(
    pool: asyncpg.Pool,
    doc_id: str,
    page_number: int,
    confidence_threshold: float = 0.65,
) -> list[dict]:
    """Return blocks on a page that are below the confidence threshold and not yet repaired."""
    rows = await pool.fetch(
        """
        SELECT b.*
          FROM book_blocks b
          JOIN book_pages  p ON p.page_id = b.page_id
         WHERE b.doc_id = $1
           AND p.page_number = $2
           AND b.ocr_confidence IS NOT NULL
           AND b.ocr_confidence < $3
           AND b.correction_status = 'none'
         ORDER BY b.block_index
        """,
        doc_id, page_number, confidence_threshold,
    )
    return [dict(r) for r in rows]

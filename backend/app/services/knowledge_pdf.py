"""Conservative text-block ordering and extraction coverage, without OCR."""

PARSER_VERSION = "pdf-block-order-v1"


def _reading_order(blocks, width):
    """Split at full-width bands; reorder only clear central-gutter columns.

    Ambiguous bands fall back to geometric top-to-bottom order. This is not a
    general layout/table/formula recognizer. Every text block is retained once.
    """
    if len(blocks) > 2000:
        return blocks, False  # Avoid quadratic layout inference on pathological pages.
    ordered = sorted(blocks, key=lambda b: (b[1], b[0]))
    middle = width / 2
    spans = [
        b
        for b in ordered
        if b[0] < middle < b[2] or (b[0] >= width * 0.42 and b[2] <= width * 0.58)
    ]
    bands, pending = [], []
    for block in ordered:
        if block in spans:
            # Overlapping spanning text makes column inference ambiguous.
            if any(b[1] < block[3] and b[3] > block[1] for b in ordered if b is not block):
                return ordered, False
            bands.append(pending)
            bands.append([block])
            pending = []
        else:
            pending.append(block)
    bands.append(pending)
    result, detected = [], False
    for band in bands:
        left = [b for b in band if b[2] <= middle]
        right = [b for b in band if b[0] >= middle]
        if left and right and len(left) + len(right) == len(band):
            gutter = min(b[0] for b in right) - max(b[2] for b in left)
            overlap = min(max(b[3] for b in left), max(b[3] for b in right)) - max(
                min(b[1] for b in left), min(b[1] for b in right)
            )
            enough_text = all(
                sum(len(b[4].strip()) for b in column) >= 120
                and sum(len(b[4].strip().splitlines()) for b in column) >= 3
                for column in [left, right]
            )
            if gutter >= 12 and overlap >= 24 and enough_text:
                result.extend(left + right)
                detected = True
                continue
        result.extend(band)
    return result, detected


def extract_pdf(data: bytes) -> tuple[list[dict], dict]:
    import pymupdf

    blocks = []
    report = {
        "parser_version": PARSER_VERSION,
        "total_pages": 0,
        "text_pages": 0,
        "empty_text_pages": [],
        "suspected_scan_pages": [],
        "two_column_pages": [],
    }
    characters = 0
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("PDF 已加密，请上传解除密码保护的副本。")
        if len(doc) > 500:
            raise ValueError("文档超过 500 页，请拆分后上传。")
        report["total_pages"] = len(doc)
        for number, page in enumerate(doc, 1):
            raw = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
            if characters + sum(len(b[4]) for b in raw) > 1_000_000:
                raise ValueError("文档文字过多，请拆分后上传。")
            # Rotated/cropped coordinate spaces are not suitable for this heuristic.
            if page.rotation or page.cropbox != page.mediabox:
                ordered, columns = raw, False
            else:
                ordered, columns = _reading_order(raw, page.rect.width)
            text = "\n".join(b[4].rstrip("\n") for b in ordered)
            characters += len(text)
            if characters > 1_000_000:
                raise ValueError("文档文字过多，请拆分后上传。")
            if text.strip():
                report["text_pages"] += 1
            else:
                report["empty_text_pages"].append(number)
            # Sparse text over a large raster image may be a scan with only page
            # numbers/captions extracted. Do not label figure-only pages as proven scans.
            if (
                len(text.strip()) < 80
                and page.rect.get_area() > 0
                and any(
                    (pymupdf.Rect(info["bbox"]) & page.rect).get_area()
                    >= page.rect.get_area() * 0.5
                    for info in page.get_image_info()
                )
            ):
                report["suspected_scan_pages"].append(number)
            if columns:
                report["two_column_pages"].append(number)
            blocks.append({"page": number, "text": text, "location": {}})
    return blocks, report

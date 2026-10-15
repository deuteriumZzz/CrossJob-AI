"""Local cross-platform OCR for scanned PDFs."""

from __future__ import annotations

from collections.abc import Callable

_MAX_PAGES = 100
_MAX_RENDER_EDGE = 3_000
_MAX_RENDER_PIXELS = 12_000_000


def recognize_pdf_pages(
    data: bytes,
    page_numbers: list[int],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[int, str]:
    """Render selected 1-based PDF pages and recognize Russian/English text.

    PDFium and RapidOCR run locally on Windows and macOS; no document content
    is sent to a third-party OCR service. RapidOCR may download its selected
    recognition model on the first use.
    """
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
        from rapidocr import RapidOCR  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError(
            "Не установлены компоненты локального OCR. Переустановите "
            "зависимости приложения командой "
            "pip install -r requirements-desktop.txt."
        ) from error

    document = pdfium.PdfDocument(data)
    page_count = len(document)
    if page_count > _MAX_PAGES:
        document.close()
        raise ValueError(
            f"В PDF {page_count} страниц. Для OCR поддерживаются файлы "
            f"до {_MAX_PAGES} страниц."
        )

    recognized: dict[int, str] = {}
    total = len(page_numbers)
    if on_progress:
        on_progress(0, total)
    try:
        try:
            engine = RapidOCR(
                params={
                    "Rec.ocr_version": "PP-OCRv5",
                    "Rec.lang_type": "cyrillic",
                    "Rec.model_type": "mobile",
                }
            )
        except Exception as error:
            raise ValueError(
                "Не удалось подготовить OCR-модель. Проверьте подключение "
                "к интернету и повторите импорт."
            ) from error
        for index, page_number in enumerate(page_numbers, start=1):
            page = document[page_number - 1]
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                recognized[page_number] = ""
                continue
            scale = min(2.0, _MAX_RENDER_EDGE / max(width, height))
            pixel_width = max(1, int(width * scale))
            pixel_height = max(1, int(height * scale))
            if pixel_width * pixel_height > _MAX_RENDER_PIXELS:
                scale *= (
                    _MAX_RENDER_PIXELS / (pixel_width * pixel_height)
                ) ** 0.5
            bitmap = page.render(scale=scale)
            try:
                try:
                    result = engine(bitmap.to_pil())
                except Exception as error:
                    raise ValueError(
                        "Не удалось распознать текст на странице "
                        f"PDF №{page_number}."
                    ) from error
                recognized[page_number] = "\n".join(result.txts or [])
            finally:
                bitmap.close()
                page.close()
            if on_progress:
                on_progress(index, total)
    finally:
        document.close()
    return recognized

from __future__ import annotations

import io


class OcrValidationError(ValueError):
    pass


class OcrService:
    """
    Extract text from a CV file.
    Strategy:
    1. Try PyMuPDF (fast, native PDF text).
    2. Fall back to Azure Document Intelligence if word count < 50 OR printable ratio < 0.90.
    3. Raise OcrValidationError for corrupt/encrypted files.
    """

    async def extract(self, file_bytes: bytes, filename: str = "cv.pdf") -> tuple[str, str]:
        """
        Returns (cv_text, extraction_method).
        extraction_method: 'pymupdf' | 'document_intelligence'
        """
        try:
            text, method = await self._try_pymupdf(file_bytes)
            if self._quality_ok(text):
                return text, method
            return await self._azure_doc_intelligence(file_bytes)
        except OcrValidationError:
            raise
        except Exception as exc:
            raise OcrValidationError(f"corrupted_pdf: {exc}") from exc

    async def _try_pymupdf(self, file_bytes: bytes) -> tuple[str, str]:
        import fitz  # PyMuPDF

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise OcrValidationError(f"corrupted_pdf: {exc}") from exc

        if doc.is_encrypted:
            raise OcrValidationError("encrypted_pdf")

        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())
        doc.close()
        return "\n".join(pages_text), "pymupdf"

    def _quality_ok(self, text: str) -> bool:
        words = text.split()
        if len(words) < 50:
            return False
        printable = sum(1 for c in text if c.isprintable())
        total = max(len(text), 1)
        if printable / total < 0.90:
            return False
        return True

    async def _azure_doc_intelligence(self, file_bytes: bytes) -> tuple[str, str]:
        from app.config import get_settings
        from azure.ai.formrecognizer.aio import DocumentAnalysisClient
        from azure.core.credentials import AzureKeyCredential

        settings = get_settings()
        client = DocumentAnalysisClient(
            endpoint=settings.AZURE_FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_FORM_RECOGNIZER_KEY),
        )
        async with client:
            poller = await client.begin_analyze_document("prebuilt-document", file_bytes)
            result = await poller.result()

        text = "\n".join(p.content for p in result.paragraphs or [])
        if not text.strip():
            raise OcrValidationError("no_text_extracted")
        return text, "document_intelligence"

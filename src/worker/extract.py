"""Text extraction from PDF documents using PyMuPDF.

Extracts all text content from a PDF file, preserving page structure.
This is the first stage of the document processing pipeline.
"""

from dataclasses import dataclass

import fitz


@dataclass
class ExtractionResult:
    """Result of extracting text from a PDF."""

    text: str
    page_count: int
    word_count: int
    char_count: int


def extract_text(pdf_bytes: bytes) -> ExtractionResult:
    """Extract all text from a PDF document.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        ExtractionResult with the extracted text and metadata.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    full_text = "\n\n".join(pages)
    words = full_text.split()

    return ExtractionResult(
        text=full_text,
        page_count=len(pages),
        word_count=len(words),
        char_count=len(full_text),
    )

import base64
import io
import logging

_logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".csv", ".docx", ".xls", ".xlsx")


def is_supported(filename):
    return (filename or "").lower().endswith(SUPPORTED_EXTENSIONS)


def extract_text(data, filename):
    """Extract plain text from a file's raw bytes based on its extension.

    Returns the extracted text on success, an error sentinel string on
    recoverable failure, or "" when input is missing.
    """
    if not data:
        return ""

    name = (filename or "").lower()

    if name.endswith(".pdf"):
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except Exception as e:
            _logger.error("Error extracting PDF (%s): %s", filename, e)
            return f"Error processing PDF file: {e}"

    if name.endswith((".txt", ".md", ".csv")):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="ignore")

    if name.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            _logger.error("Error extracting DOCX (%s): %s", filename, e)
            return f"Error processing DOCX file: {e}"

    if name.endswith((".xls", ".xlsx")):
        try:
            import pandas as pd
            df_dict = pd.read_excel(io.BytesIO(data), sheet_name=None)
            parts = []
            for sheet, df in df_dict.items():
                parts.append(f"=== Sheet: {sheet} ===\n\n{df.to_string(index=False)}")
            return "\n\n".join(parts).strip()
        except Exception as e:
            _logger.error("Error extracting Excel (%s): %s", filename, e)
            return f"Error processing Excel file: {e}"

    return "Unsupported file type"


def extract_text_from_attachment(attachment):
    """Convenience wrapper for ir.attachment records (decodes datas)."""
    if not attachment or not attachment.datas:
        return ""
    try:
        data = base64.b64decode(attachment.datas)
    except Exception as e:
        _logger.warning("Could not decode attachment %s: %s", attachment.id, e)
        return ""
    return extract_text(data, attachment.name or "")

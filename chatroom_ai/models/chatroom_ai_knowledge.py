"""Knowledge Base - Documents and context for AI agents"""

import base64
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatroomAIKnowledge(models.Model):
    _name = "chatroom.ai.knowledge"
    _description = "AI Agent Knowledge Base"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    content_type = fields.Selection(
        [
            ("text", "Plain Text"),
            ("html", "HTML"),
            ("file", "File Upload"),
        ],
        required=True,
        default="text",
    )
    content = fields.Text(
        help="Direct text content or processed file content",
    )
    file = fields.Binary(
        attachment=True,
    )
    file_name = fields.Char()

    description = fields.Text()
    tag_ids = fields.Many2many(
        "chatroom.ai.knowledge.tag",
        "chatroom_ai_knowledge_tag_rel",
        "knowledge_id",
        "tag_id",
    )

    processing_status = fields.Selection(
        [
            ("not_processed", "Not Processed"),
            ("success", "Success"),
            ("error", "Error"),
        ],
        default="not_processed",
        readonly=True,
    )
    processing_message = fields.Text(
        readonly=True,
        help="Success message or error details",
    )
    processed_content = fields.Text(
        readonly=True,
        help="Cleaned and formatted content ready for AI consumption",
    )
    char_count = fields.Integer(
        compute="_compute_char_count",
        store=True,
    )

    agent_ids = fields.Many2many(
        "chatroom.ai.agent",
        "chatroom_ai_agent_knowledge_rel",
        "knowledge_id",
        "agent_id",
    )
    last_updated = fields.Datetime(readonly=True, default=fields.Datetime.now)

    @api.depends("processed_content")
    def _compute_char_count(self):
        for record in self:
            record.char_count = len(record.processed_content or "")

    def action_process_content(self):
        for record in self:
            try:
                if record.content_type == "text":
                    record.processed_content = record.content
                    record.processing_status = "success"
                    record.processing_message = "Text content loaded successfully"

                elif record.content_type == "html":
                    import re

                    text = re.sub("<[^<]+?>", "", record.content or "")
                    record.processed_content = text.strip()
                    record.processing_status = "success"
                    record.processing_message = (
                        "HTML processed and cleaned successfully"
                    )

                elif record.content_type == "file":
                    result = record._extract_text_from_file()
                    record.processed_content = result

                    if (
                        result.startswith("Unsupported file type")
                        or result.startswith("Install")
                        or result.startswith("Error")
                    ):
                        record.processing_status = "error"
                        record.processing_message = result
                    else:
                        record.processing_status = "success"
                        record.processing_message = (
                            "File processed successfully: "
                            f"{len(result)} characters extracted"
                        )

                record.last_updated = fields.Datetime.now()

            except Exception as e:
                _logger.error(f"Error processing knowledge {record.name}: {str(e)}")
                record.processing_status = "error"
                record.processing_message = f"Error: {str(e)}"
                raise

    def _extract_text_from_file(self):
        if not self.file:
            return ""

        file_data = base64.b64decode(self.file)
        file_name = self.file_name or ""

        if file_name.lower().endswith(".pdf"):
            try:
                import io

                import PyPDF2

                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
            except ImportError:
                _logger.warning("PyPDF2 not installed, cannot extract PDF")
                return ""

        elif file_name.lower().endswith((".txt", ".md", ".csv")):
            try:
                return file_data.decode("utf-8")
            except UnicodeDecodeError:
                return file_data.decode("latin-1", errors="ignore")

        elif file_name.lower().endswith(".docx"):
            try:
                import io

                import docx

                doc = docx.Document(io.BytesIO(file_data))
                return "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                _logger.warning("python-docx not installed, cannot extract DOCX")
                return ""

        elif file_name.lower().endswith((".xls", ".xlsx")):
            try:
                import io

                import pandas as pd

                df_dict = pd.read_excel(io.BytesIO(file_data), sheet_name=None)

                text = ""
                for sheet_name, df in df_dict.items():
                    text += f"=== Sheet: {sheet_name} ===\n\n"
                    text += df.to_string(index=False)
                    text += "\n\n"

                return text.strip()
            except ImportError:
                _logger.warning(
                    "pandas and openpyxl not installed, cannot extract Excel"
                )
                return "Install 'pandas' and 'openpyxl' to process Excel files"
            except Exception as e:
                _logger.error(f"Error extracting Excel: {str(e)}")
                return f"Error processing Excel file: {str(e)}"

        else:
            return "Unsupported file type"

    def get_formatted_content(self):
        self.ensure_one()

        if not self.processed_content:
            self.action_process_content()

        formatted = f"=== Document: {self.name} ===\n"
        if self.description:
            formatted += f"Description: {self.description}\n"
        formatted += f"\n{self.processed_content}\n"
        formatted += "=" * 50 + "\n\n"

        return formatted

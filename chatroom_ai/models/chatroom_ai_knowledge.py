import base64
import logging

from odoo import api, fields, models

from ..utils.text_extraction import extract_text

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
                _logger.error("Error processing knowledge %s: %s", record.name, e)
                record.processing_status = "error"
                record.processing_message = f"Error: {str(e)}"
                raise

    def _extract_text_from_file(self):
        if not self.file:
            return ""
        return extract_text(base64.b64decode(self.file), self.file_name or "")

    def get_formatted_content(self):
        self.ensure_one()

        if not self.processed_content:
            _logger.warning(
                "Knowledge '%s' (ID=%d) has no processed content. "
                "Run 'Process Content' to populate it.",
                self.name,
                self.id,
            )
            return ""

        formatted = f"=== Document: {self.name} ===\n"
        if self.description:
            formatted += f"Description: {self.description}\n"
        formatted += f"\n{self.processed_content}\n"
        formatted += "=" * 50 + "\n\n"

        return formatted

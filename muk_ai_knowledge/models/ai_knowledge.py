import base64
import logging
import re

from odoo import api, fields, models

from ..utils.text_extraction import extract_text

_logger = logging.getLogger(__name__)


class AIKnowledge(models.Model):
    _name = "muk_ai.knowledge"
    _description = "AI Knowledge Base"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()

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
        help="Direct text content or raw HTML; for files use the file field.",
    )
    file = fields.Binary(attachment=True)
    file_name = fields.Char()

    processed_content = fields.Text(
        readonly=True,
        help="Cleaned and extracted content ready for AI consumption.",
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
    processing_message = fields.Text(readonly=True)
    char_count = fields.Integer(compute="_compute_char_count", store=True)
    last_updated = fields.Datetime(readonly=True, default=fields.Datetime.now)

    agent_ids = fields.Many2many(
        "muk_ai.agent",
        "muk_ai_agent_knowledge_rel",
        "knowledge_id",
        "agent_id",
        string="Agents",
    )

    @api.depends("processed_content")
    def _compute_char_count(self):
        for record in self:
            record.char_count = len(record.processed_content or "")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_process_content()
        return records

    def write(self, vals):
        result = super().write(vals)
        if any(k in vals for k in ("content", "file", "file_name", "content_type")):
            self.action_process_content()
        return result

    def action_process_content(self):
        for record in self:
            try:
                if record.content_type == "text":
                    record.processed_content = record.content or ""
                    record.processing_status = "success"
                    record.processing_message = "Text content loaded."

                elif record.content_type == "html":
                    stripped = re.sub(r"<[^<]+?>", "", record.content or "")
                    record.processed_content = stripped.strip()
                    record.processing_status = "success"
                    record.processing_message = "HTML stripped to plain text."

                elif record.content_type == "file":
                    result = record._extract_text_from_file()
                    record.processed_content = result
                    if result.startswith(("Unsupported file type", "Install", "Error")):
                        record.processing_status = "error"
                        record.processing_message = result
                    else:
                        record.processing_status = "success"
                        record.processing_message = (
                            f"File processed: {len(result)} characters extracted."
                        )

                record.last_updated = fields.Datetime.now()
            except Exception as e:
                _logger.error("Error processing knowledge %s: %s", record.name, e)
                record.processing_status = "error"
                record.processing_message = f"Error: {e}"

    def _extract_text_from_file(self):
        if not self.file:
            return ""
        return extract_text(base64.b64decode(self.file), self.file_name or "")

    def get_formatted_content(self):
        """Return the KB formatted as a block ready to be inlined in a prompt."""
        self.ensure_one()
        if not self.processed_content:
            return ""
        parts = [f"=== Document: {self.name} ==="]
        if self.description:
            parts.append(f"Description: {self.description}")
        parts.append("")
        parts.append(self.processed_content)
        parts.append("=" * 50)
        return "\n".join(parts)

import logging

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.addons.muk_mcp.core.tool import mcp_tool

from ..utils.text_extraction import (
    extract_text_from_attachment,
    is_supported,
    SUPPORTED_EXTENSIONS,
)

_logger = logging.getLogger(__name__)


class MukAIKnowledgeTools(models.AbstractModel):
    _inherit = "muk_mcp.mixin"

    @api.model
    @mcp_tool(
        name="create_knowledge_from_attachment",
        description=(
            "Create a muk_ai.knowledge record by extracting text from an "
            "uploaded file attachment. Use this when a business owner pastes "
            "a PDF (catalog), Word/Excel doc, or text file in the chat and "
            "wants its content turned into a knowledge base. Supported "
            "extensions: " + ", ".join(SUPPORTED_EXTENSIONS) + ". "
            "Optionally pass agent_id to immediately link the new KB to a "
            "muk_ai.agent."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "attachment_id": {
                    "type": "integer",
                    "description": "ID of the ir.attachment to ingest.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Human-friendly name for the new knowledge base "
                        "(e.g. 'Catálogo La Norteña - 2026')."
                    ),
                },
                "agent_id": {
                    "type": ["integer", "null"],
                    "description": (
                        "Optional muk_ai.agent ID to link the new KB to."
                    ),
                },
                "description": {
                    "type": ["string", "null"],
                    "description": "Optional description for the KB record.",
                },
            },
            "required": ["attachment_id", "name"],
        },
        category="write",
        registry="odoo",
    )
    def _mcp_create_knowledge_from_attachment(
        self,
        attachment_id,
        name,
        agent_id=None,
        description=None,
    ):
        attachment = self.env["ir.attachment"].sudo().browse(attachment_id)
        if not attachment.exists():
            raise UserError(_(
                "Attachment id=%(id)s does not exist.",
                id=attachment_id,
            ))
        if not is_supported(attachment.name or ""):
            raise UserError(_(
                "Attachment '%(name)s' has an unsupported extension. "
                "Supported: %(exts)s.",
                name=attachment.name,
                exts=", ".join(SUPPORTED_EXTENSIONS),
            ))

        text = extract_text_from_attachment(attachment)
        if not text or text.startswith(("Unsupported file type", "Install", "Error")):
            raise UserError(_(
                "Could not extract text from '%(name)s': %(msg)s",
                name=attachment.name,
                msg=text or "(empty)",
            ))

        vals = {
            "name": name,
            "content_type": "text",
            "content": text,
            "description": description or False,
        }
        kb = self.env["muk_ai.knowledge"].sudo().create(vals)

        if agent_id:
            agent = self.env["muk_ai.agent"].sudo().browse(agent_id)
            if agent.exists():
                agent.knowledge_ids = [(4, kb.id)]

        return {
            "id": kb.id,
            "name": kb.name,
            "char_count": kb.char_count,
            "processing_status": kb.processing_status,
            "linked_agent_id": agent_id if agent_id else None,
        }

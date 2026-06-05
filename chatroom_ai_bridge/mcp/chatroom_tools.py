from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool


class ChatroomToolsMixin(models.AbstractModel):
    _inherit = "muk_mcp.mixin"

    @api.model
    @mcp_tool(
        name="escalate_to_human",
        description=(
            "Hand off this conversation to a human operator. "
            "Use when the customer has a complaint, a return/refund request, "
            "a credit issue, or explicitly asks to speak with a person. "
            "Calling this marks the room as requiring human attention and "
            "stops the AI from auto-responding. "
            "ALWAYS call this BEFORE writing your farewell message to the customer."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Short reason for escalation visible to the operator "
                        "(e.g. 'reclamo: pedido llegó mal', 'solicitud de devolución')."
                    ),
                },
            },
            "required": [],
        },
        category="write",
        registry="odoo",
    )
    def _mcp_escalate_to_human(self, reason=""):
        session_id = self.env.context.get("muk_mcp_session_id")
        if not session_id:
            raise UserError(_(
                "escalate_to_human can only be called from within an AI session."
            ))
        room = self.env["chatroom.room"].sudo().search(
            [("muk_ai_session_id", "=", session_id)], limit=1
        )
        if not room:
            raise UserError(_("No chatroom room is linked to this session."))
        room.write({"needs_attention": True, "ai_active": False})
        return {
            "status": "escalated",
            "room": room.name,
            "reason": reason or "",
            "message": "Operator notified. AI has stopped responding to this conversation.",
        }

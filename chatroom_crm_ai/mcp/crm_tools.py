from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool

# How many trailing messages of the chat to embed in the lead description.
_TRANSCRIPT_LIMIT = 15


class ChatroomCrmAiTools(models.AbstractModel):
    _inherit = "muk_mcp.mixin"

    def _crm_ai_room_from_session(self):
        """Return the chatroom.room bound to the current AI session, or raise."""
        session_id = self.env.context.get("muk_mcp_session_id")
        if not session_id:
            raise UserError(_(
                "create_crm_lead can only be called from within an AI session."
            ))
        room = self.env["chatroom.room"].sudo().search(
            [("muk_ai_session_id", "=", session_id)], limit=1
        )
        if not room:
            raise UserError(_("No chatroom room is linked to this session."))
        return room

    def _crm_ai_transcript(self, room):
        """Short plain-text transcript of the last messages of the room."""
        messages = room.message_ids.sorted("id")[-_TRANSCRIPT_LIMIT:]
        lines = []
        for message in messages:
            who = "Cliente" if message.direction == "incoming" else "Asistente"
            body = (message.body or "").strip()
            if body:
                lines.append(f"{who}: {body}")
        return "\n".join(lines)

    def _crm_ai_build_description(self, room, summary):
        parts = [
            (summary or "").strip(),
            "",
            f"— Generado automáticamente por el asistente IA desde el chat "
            f"'{room.name or room.id}'.",
        ]
        transcript = self._crm_ai_transcript(room)
        if transcript:
            parts += ["", "Conversación:", transcript]
        return "\n".join(p for p in parts if p is not None)

    @api.model
    @mcp_tool(
        name="create_crm_lead",
        description=(
            "Register a sales lead when the customer shows concrete commercial "
            "intent (wants to hire/buy/subscribe, asks for a quote, or asks to "
            "be contacted). Links the lead to the current chat. Do NOT use it "
            "for greetings or trivial questions. One lead per conversation: if "
            "one already exists for this chat it is updated, not duplicated."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "Short summary of what the customer wants / their "
                        "interest, in the customer's language."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Optional short title for the lead.",
                },
                "contact_name": {
                    "type": "string",
                    "description": "Customer full name, if known.",
                },
                "phone": {
                    "type": "string",
                    "description": "Customer phone number, if known.",
                },
                "email": {
                    "type": "string",
                    "description": "Customer email, if known.",
                },
                "expected_revenue": {
                    "type": "number",
                    "description": "Estimated deal value, if it can be inferred.",
                },
            },
            "required": ["summary"],
        },
        category="write",
        registry="odoo",
    )
    def _mcp_create_crm_lead(
        self,
        summary,
        title=None,
        contact_name=None,
        phone=None,
        email=None,
        expected_revenue=None,
    ):
        room = self._crm_ai_room_from_session()
        Lead = self.env["crm.lead"].sudo()

        # Dedup: reuse an OPEN lead already linked to this room; if the existing
        # ones are closed (lost = archived, or won), create a fresh lead.
        existing = Lead.with_context(active_test=False).search(
            [("chatroom_room_ids", "in", room.id)]
        )
        open_lead = existing.filtered(
            lambda lead: lead.active and not lead.stage_id.is_won
        )[:1]

        if open_lead:
            stamp = fields.Datetime.to_string(fields.Datetime.now())
            addition = f"\n\n— Actualización ({stamp}):\n{(summary or '').strip()}"
            open_lead.write({"description": (open_lead.description or "") + addition})
            return {
                "status": "updated",
                "lead_id": open_lead.id,
                "name": open_lead.name,
                "type": open_lead.type,
                "message": "Existing open lead updated with the new information.",
            }

        partner = room.partner_ids[:1]
        lead_type = "lead" if room.muk_ai_agent_id.crm_lead_enabled else "opportunity"
        final_name = (
            (title or "").strip()
            or f"Interés vía chat — {contact_name or partner.name or room.name}"
        )

        lead = Lead.create({
            "name": final_name,
            "type": lead_type,
            "partner_id": partner.id or False,
            "contact_name": contact_name or partner.name or room.name or False,
            "phone": phone or partner.phone or room.external_id or False,
            "email_from": email or partner.email or False,
            "description": self._crm_ai_build_description(room, summary),
            "expected_revenue": expected_revenue or 0.0,
            "chatroom_room_ids": [(4, room.id)],
            "user_id": room.assigned_to_id.id or False,
        })

        return {
            "status": "created",
            "lead_id": lead.id,
            "name": lead.name,
            "type": lead_type,
            "message": "Lead registered and linked to the chat.",
        }

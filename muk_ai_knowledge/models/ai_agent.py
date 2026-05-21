from odoo import fields, models


class AIAgent(models.Model):
    _inherit = "muk_ai.agent"

    knowledge_ids = fields.Many2many(
        "muk_ai.knowledge",
        "muk_ai_agent_knowledge_rel",
        "agent_id",
        "knowledge_id",
        string="Knowledge Bases",
    )
    kb_mode = fields.Selection(
        [
            ("inline", "Inline (concatenated in system prompt)"),
            ("tool", "Tool (searchable on demand)"),
        ],
        default="inline",
        required=True,
        help=(
            "Inline: concatenates knowledge base contents into the system prompt "
            "at session start (best for small KBs). "
            "Tool: exposes a search_knowledge tool the agent can call (best for "
            "large KBs — not implemented yet)."
        ),
    )

    def _build_system_prompt(self, session=None):
        base_prompt = super()._build_system_prompt(session=session)
        self.ensure_one()
        if self.kb_mode != "inline" or not self.knowledge_ids:
            return base_prompt
        blocks = [
            kb.get_formatted_content()
            for kb in self.knowledge_ids.filtered(
                lambda k: k.processing_status == "success" and k.processed_content
            )
        ]
        if not blocks:
            return base_prompt
        preamble = (
            "\n\n=== KNOWLEDGE BASE ===\n"
            "Use the following documents as your authoritative source for "
            "questions about this business. Answer from them directly when "
            "the question is covered.\n\n"
        )
        kb_section = preamble + "\n\n".join(blocks)
        return (base_prompt or "") + kb_section

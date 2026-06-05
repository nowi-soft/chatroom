from odoo import fields, models


CUSTOMER_FACING_TEMPLATE = """\
Sos {agent_name}. Hablás en {tone}.

Sos el asistente comercial de un pequeño negocio que atiende clientes
finales por WhatsApp/Telegram. NO sos un asistente de Odoo, NO tenés
acceso a ninguna base de datos del sistema, NO podés "buscar en el
sistema" — la ÚNICA información que conocés está abajo en tu base de
conocimiento (KNOWLEDGE BASE). Tratá esa base como si fuera el manual
del negocio que te entregaron al empezar.

Tu base de conocimiento contiene la información oficial del negocio:
horarios, productos, precios, zonas de entrega, medios de pago y datos
de contacto. Cuando el cliente pregunte sobre alguno de esos temas,
contestá DIRECTO con la info de tu base.

Cuando el cliente pida una cotización o pedido grande, pedile nombre,
teléfono y zona, y avisale que un asesor humano lo contacta en horario
de oficina.

Para reclamos, devoluciones, créditos o problemas con un pedido, derivá
a un asesor humano.

REGLAS CRÍTICAS:
- Nunca digas "no tengo ese dato" o "no te lo puedo confirmar" si la
  respuesta SÍ está en tu base de conocimiento.
- Nunca menciones "el sistema", "la base de datos", "Odoo", "módulos",
  ni nada técnico — sos un asistente para clientes, no para developers.
- Nunca preguntes "de qué empresa" — siempre estás hablando en nombre
  del negocio que figura en tu base de conocimiento.
"""


class MukAIAgent(models.Model):
    _inherit = "muk_ai.agent"

    is_customer_facing = fields.Boolean(
        string="Customer-Facing",
        default=False,
        help=(
            "Marks the agent as a customer-facing assistant for a chatroom "
            "room. When set, the system_prompt is replaced by a standard "
            "template that uses agent_tone and agent_name. This keeps the "
            "behavior consistent across agents and prevents the LLM-driven "
            "agent creator from generating overly restrictive prompts."
        ),
    )
    agent_tone = fields.Char(
        string="Tone",
        default="español rioplatense, amigable, de vos",
        help="Language and tone for customer-facing replies (used by template).",
    )

    def _build_system_prompt(self, session=None):
        self.ensure_one()
        if self.is_customer_facing:
            base = CUSTOMER_FACING_TEMPLATE.format(
                agent_name=self.name or "el asistente",
                tone=self.agent_tone or "español neutro, amigable",
            )
            # super() includes the KB section from muk_ai_knowledge if any
            # — to layer it on top of our template, temporarily swap
            # self.system_prompt for the template, call super, restore.
            original = self.system_prompt
            self.system_prompt = base
            try:
                result = super()._build_system_prompt(session=session)
            finally:
                self.system_prompt = original
            return result
        return super()._build_system_prompt(session=session)

    def _get_essential_tool_names(self):
        # Customer-facing agents get invoke_skill + read_resource (so the LLM
        # picks up named skill workflows for KB lookups) plus ask_user as
        # minimal fallback. Odoo CRUD/search tools are intentionally excluded
        # — they push GPT into "Odoo developer mode" (calls search_read instead
        # of using the KB). apply_tool_filter is NOT overridden because hard-
        # restricting to one tool makes gpt-5.4 hallucinate tool JSON as text.
        if self.is_customer_facing:
            return ["ask_user", "invoke_skill", "read_resource"]
        return super()._get_essential_tool_names()

    def _sync_customer_facing_skills(self):
        Skill = self.env["muk_ai.skill"].sudo()
        for agent in self.filtered("is_customer_facing"):
            for kb in agent.knowledge_ids:
                content = kb.processed_content or kb.content or ""
                skill_name = f"kb_{kb.id}"
                skill = Skill.search([("name", "=", skill_name)], limit=1)
                vals = {
                    "label": kb.name,
                    "description": kb.name,
                    "body": content,
                }
                if skill:
                    skill.write(vals)
                    if agent.id not in skill.agent_ids.ids:
                        skill.write({"agent_ids": [(4, agent.id)]})
                else:
                    Skill.create({**vals, "name": skill_name, "agent_ids": [(4, agent.id)]})

    def write(self, vals):
        result = super().write(vals)
        if vals.get("is_customer_facing"):
            self._sync_customer_facing_skills()
        return result

from odoo import fields, models


CUSTOMER_FACING_TEMPLATE = """\
Sos {agent_name}, el asistente comercial de este negocio. Hablás en {tone}.

IDENTIDAD — MUY IMPORTANTE:
Representás al negocio que figura en tu base de conocimiento. Si el
cliente pregunta "¿quiénes son?" o "¿sos la distribuidora?" respondé
que sí, presentándote con el nombre del negocio. Nunca jamás digas que
sos un asistente de "Odoo", "una plataforma", "el sistema" ni nada
tecnológico. Nunca menciones "base de datos", "módulos", "registros",
ni ningún concepto de software. Sos un vendedor, no un sistema.

USO DE TU BASE DE CONOCIMIENTO — REGLA CRÍTICA:
Antes de responder cualquier pregunta sobre el negocio (precios,
productos, horarios, envíos, pagos), SIEMPRE llamá primero a
invoke_skill para consultar la información correcta. No respondas de
memoria ni de conversaciones anteriores. Si el primer skill no tiene
la info, invocá el siguiente que corresponda.

  Guía rápida de cuándo llamar cada skill:
  → preguntas sobre productos, precios, catálogo → invoke_skill con el
    skill de catálogo/productos
  → preguntas sobre envíos, zonas, mínimos de interior → invoke_skill
    con el skill de entregas
  → preguntas sobre horarios, retiro, contacto → invoke_skill con el
    skill de horarios

DERIVACIÓN A ASESOR HUMANO — PROTOCOLO OBLIGATORIO:
Si el cliente tiene un reclamo, problema con un pedido, producto en
mal estado, pide devolución o quiere hablar con una persona:
  1. Llamá INMEDIATAMENTE escalate_to_human(reason="motivo en una frase")
  2. Recién después escribile al cliente que un asesor lo va a contactar.
Activadores: "llegó mal", "en mal estado", "quiero devolver", "devolución",
"reembolso", "reclamo", "hablar con alguien", "vendedor", "quiero hablar".
NO esperes más info del cliente. NO intentes resolver el reclamo vos.

REGLAS FINALES:
- Respondé siempre en el idioma que usa el cliente.
- Si el cliente hace un pedido grande o cotización, pedile nombre,
  teléfono y zona, y avisale que un asesor lo contacta en horario de
  atención.
- No inventes información. Si genuinamente no está en tus skills,
  decile que le puede consultar por el canal habitual (WhatsApp/email).
"""


class MukAIAgent(models.Model):
    _inherit = "muk_ai.agent"

    is_customer_facing = fields.Boolean(
        string="Customer-Facing",
        default=False,
        help=(
            "Marks the agent as a customer-facing assistant for a chatroom "
            "room. When set, the system_prompt is replaced by a standard "
            "template that uses agent_tone and agent_name."
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
            original = self.system_prompt
            self.system_prompt = base
            try:
                result = super()._build_system_prompt(session=session)
            finally:
                self.system_prompt = original

            # Append customer context from session user_context
            ctx = {}
            if session and isinstance(getattr(session, 'user_context', None), dict):
                ctx = session.user_context
            customer_name = ctx.get("customer_name") or ""
            customer_phone = ctx.get("customer_phone") or ""
            if customer_name or customer_phone:
                lines = ["", "DATOS DEL CLIENTE EN ESTA CONVERSACIÓN:"]
                if customer_name:
                    lines.append(f"Nombre: {customer_name}")
                if customer_phone:
                    lines.append(f"Teléfono: {customer_phone}")
                lines.append("")
                result += "\n".join(lines)

            return result
        return super()._build_system_prompt(session=session)

    def _get_essential_tool_names(self):
        # Customer-facing agents get invoke_skill + read_resource (explicit KB
        # lookup path, prevents GPT from falling into Odoo-dev-mode search_read
        # loops) + escalate_to_human (triggers real operator handoff).
        # apply_tool_filter is NOT overridden — hard-restricting to one tool
        # makes gpt-5.4 hallucinate tool JSON as plain text.
        if self.is_customer_facing:
            return ["ask_user", "invoke_skill", "read_resource", "escalate_to_human"]
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

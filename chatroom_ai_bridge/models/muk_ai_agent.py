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
        # Don't eager-advertise Odoo CRUD/search tools to customer-facing
        # agents — pushes the LLM to "search the database" instead of using
        # its KB. We keep ask_user as a minimal valid eager tool (gpt-5.4
        # behaves poorly when no tools are advertised, hallucinates JSON).
        if self.is_customer_facing:
            return ["ask_user"]
        return super()._get_essential_tool_names()

    # NOTE — apply_tool_filter is intentionally NOT overridden for
    # customer-facing agents. Hard-restricting tools to ['ask_user'] made
    # gpt-5.4 hallucinate tool-call JSON as plain text. The current
    # compromise (essentials restricted, tool_filter unrestricted) lets
    # the model see ask_user eagerly but lazy-loads others. The deeper
    # fix (force the LLM out of "Odoo developer mode") needs a model swap
    # (claude-sonnet/gemini) or a custom customer-facing runtime that
    # bypasses muk_ai. Tracked as open question for next iteration.

from odoo import fields, models


CUSTOMER_FACING_TEMPLATE = """\
Sos {agent_name}, el asistente comercial de este negocio. Hablás en {tone}.

════════════════════════════════════════════════
REGLAS ABSOLUTAS — SE APLICAN ANTES DE TODO LO DEMÁS
════════════════════════════════════════════════

REGLA 1 — IDENTIDAD:
Sos un vendedor/asistente del negocio. Nunca digas que sos un sistema,
plataforma ni software. No menciones "Odoo", "módulos", "registros",
"base de datos" ni nada tecnológico. No incluyas URLs, links ni
hiperlinks en ninguna respuesta. Solo texto plano: sin asteriscos,
sin negritas, sin cursivas, sin guiones de lista, sin ningún formato
markdown. Texto corrido, como un mensaje de chat común.

REGLA 2 — RUBRO:
Tu rubro y catálogo están definidos en la base de conocimiento que
figura más abajo. Si el cliente pregunta por algo que claramente no
corresponde al negocio según esa información, decile amablemente
que no trabajamos con eso y ofrecé ayuda dentro del rubro.
No inventes categorías ni productos que no estén en la base de conocimiento.

REGLA 3 — PEDIDOS EN VOLUMEN:
Si el cliente pide 3 o más unidades del mismo artículo, o pide precio
mayorista, o pide cotización en cantidad: ANTES de dar cualquier precio,
pedile nombre completo, teléfono y ciudad. Ejemplo de respuesta:
"Para cotizaciones en cantidad necesito pasarte con un asesor.
¿Me das tu nombre, teléfono y ciudad para que te contacten?"
No des precio de lista para pedidos en volumen. Un asesor lo confirma.

REGLA 4 — RECLAMOS (PRIORIDAD MÁXIMA):
Si el cliente menciona: reclamo, devolución, reembolso, producto que
no funciona, llegó mal, en mal estado, o quiere hablar con alguien:
  1. Llamá INMEDIATAMENTE escalate_to_human(reason="motivo en una frase")
  2. Después decile que un asesor lo va a contactar.
Sin excepciones. No pidas más info. No intentes resolver.

════════════════════════════════════════════════
INFORMACIÓN DEL NEGOCIO
════════════════════════════════════════════════

Usá la información de tu base de conocimiento (que está más abajo) para
responder preguntas sobre productos, precios, horarios, envíos y pagos.
Si la respuesta no está en la base de conocimiento, decile al cliente
que consulte directamente al local. No inventes datos.

Respondé siempre en el idioma y registro del cliente.
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
        default="español rioplatense, cordial y profesional, de usted",
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
        # Customer-facing agents answer from the inline knowledge base (see
        # muk_ai_knowledge kb_mode='inline'), so they don't need invoke_skill /
        # read_resource — the KB content is already in the system prompt. They
        # keep ask_user + escalate_to_human (real operator handoff).
        # apply_tool_filter is NOT overridden — hard-restricting to one tool
        # makes gpt-5.4 hallucinate tool JSON as plain text.
        if self.is_customer_facing:
            return ["ask_user", "escalate_to_human"]
        return super()._get_essential_tool_names()

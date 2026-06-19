from odoo import fields, models

LEAD_CAPTURE_INSTRUCTIONS = """

════════════════════════════════════════════════
CAPTACIÓN DE LEADS
════════════════════════════════════════════════

Cuando el cliente muestre una intención comercial concreta —quiere contratar,
comprar, asociarse, pedir una cotización, reservar, o pide explícitamente que
lo contacten— y tengas al menos su nombre o su teléfono, registrá el interés
llamando a la herramienta create_crm_lead.

Pasale un resumen claro de lo que el cliente quiere (summary) y los datos de
contacto que tengas (contact_name, phone, email). Si no tenés el dato, no lo
inventes: dejalo vacío.

No generes un lead por saludos, dudas triviales, o preguntas de información
general. Registrá un solo lead por conversación: si ya registraste uno en este
chat, no vuelvas a llamar la herramienta salvo que haya información nueva
importante para agregar.

No le menciones al cliente nada sobre "leads", "CRM" ni el registro interno:
seguí la conversación con naturalidad.
"""


class MukAIAgent(models.Model):
    _inherit = "muk_ai.agent"

    crm_lead_enabled = fields.Boolean(
        string="Capture as Lead (else Opportunity)",
        default=True,
        help=(
            "When enabled, leads captured by this agent are created as a CRM "
            "Lead. When disabled, they are created directly as an Opportunity. "
            "Lead capture itself is available to all customer-facing agents."
        ),
    )

    def _get_essential_tool_names(self):
        names = super()._get_essential_tool_names()
        if self.is_customer_facing and "create_crm_lead" not in names:
            names = names + ["create_crm_lead"]
        return names

    def _build_system_prompt(self, session=None):
        result = super()._build_system_prompt(session=session)
        if self.is_customer_facing:
            result += LEAD_CAPTURE_INSTRUCTIONS
        return result

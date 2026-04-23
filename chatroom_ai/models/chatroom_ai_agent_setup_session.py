import json
import logging
import re

from markupsafe import Markup

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_OBJECTIVE_TEXTS = {
    "leads": "capturar datos de clientes interesados como leads",
    "faq": "responder las consultas frecuentes de los clientes",
    "both": (
        "responder consultas frecuentes y, cuando el cliente muestre interés "
        "en comprar o contratar, capturar sus datos como lead"
    ),
}

_TONE_TEXTS = {
    "friendly": (
        "amigable y cercano. Usá tuteo (vos/tú), emojis con moderación y lenguaje natural.\n"  # noqa: E501
        "Ejemplo: '¡Hola! Claro que sí 😊 [info]. ¿Hay algo más en lo que te pueda ayudar?'"  # noqa: E501
    ),
    "formal": (
        "formal y profesional. Evitá emojis, usá un trato respetuoso (usted o impersonal) "  # noqa: E501
        "y lenguaje cuidado.\n"
        "Ejemplo: 'Buenos días. Con gusto le brindo la información. [info]. "
        "Quedo a su disposición para cualquier consulta adicional.'"
    ),
    "neutral": (
        "neutral y directo. Tuteo natural, sin emojis excesivos, respuestas claras y al punto.\n"  # noqa: E501
        "Ejemplo: 'Hola. Acá te cuento: [info]. Cualquier duda me avisás.'"
    ),
}

_OBJECTIVE_OPTIONS = "\n\n1️⃣ Capturar leads\n2️⃣ Responder preguntas frecuentes\n3️⃣ Ambos"

_TONE_OPTIONS = "\n\n1️⃣ Amigable\n2️⃣ Formal\n3️⃣ Neutral"

_BUSINESS_TYPE_OPTIONS = (
    "\n\n1️⃣ Distribuidora / Mayorista"
    "\n2️⃣ Comercio minorista (tienda, local)"
    "\n3️⃣ Automotriz / Motos / Vehículos"
    "\n4️⃣ Servicios (reparaciones, instalaciones, etc.)"
    "\n5️⃣ Servicios con turnos (médico, dentista, peluquería, etc.)"
    "\n6️⃣ Inmobiliaria / Propiedades"
    "\n7️⃣ Otro"
)

_LEAD_THRESHOLD_OPTIONS = (
    "\n\n1️⃣ Con cualquier consulta (capturar todos los contactos)"
    "\n2️⃣ Cuando pregunte por precio o un producto/servicio específico"
    "\n3️⃣ Solo cuando muestre intención clara de comprar o contratar"
)

_BUSINESS_TYPE_LABELS = {
    "distributor": "Distribuidora / Mayorista",
    "retail": "Comercio minorista",
    "automotive": "Automotriz / Motos / Vehículos",
    "services": "Servicios",
    "appointments": "Servicios con turnos",
    "real_estate": "Inmobiliaria / Propiedades",
    "other": "Otro",
}

_LEAD_THRESHOLD_LABELS = {
    "any_inquiry": "Cualquier consulta (captura máxima)",
    "product_interest": "Interés en precio o producto específico",
    "clear_intent": "Intención clara de comprar o contratar",
}

# Business-type-specific context injected into the system prompt.
_BUSINESS_TYPE_CONTEXTS = {
    "distributor": (
        "Trabajás con clientes que hacen pedidos al por mayor. "
        "Las consultas más frecuentes son: disponibilidad de stock, listas de precios, "
        "condiciones de pago (contado / cuenta corriente / transferencia), "
        "mínimo de pedido y zonas de reparto. "
        "Cuando un cliente consulta precios, stock o condiciones de pago, hay intención comercial real."  # noqa: E501
    ),
    "retail": (
        "Atendés clientes que compran al por menor en tu local o de forma online. "
        "Las consultas más frecuentes son: disponibilidad de productos, precios, "
        "métodos de pago, envíos y garantía. "
        "Cuando un cliente pregunta por el precio de un producto específico o su disponibilidad, "  # noqa: E501
        "hay intención comercial."
    ),
    "automotive": (
        "Vendés o reparás vehículos, motos o repuestos. "
        "Las consultas más frecuentes son: modelos disponibles, precios, planes de financiación, "  # noqa: E501
        "prueba de manejo / test drive, posventa y servicio técnico. "
        "Cuando un cliente pregunta por financiación, solicita precio de un modelo "
        "o consulta disponibilidad de stock, hay intención comercial."
    ),
    "services": (
        "Ofrecés servicios como reparaciones, mantenimiento, instalaciones, limpieza, etc. "  # noqa: E501
        "Las consultas más frecuentes son: presupuestos, disponibilidad horaria, "
        "zona de cobertura, tiempos de respuesta y garantía del trabajo. "
        "Cuando un cliente pide un presupuesto o consulta disponibilidad para un servicio, "  # noqa: E501
        "hay intención comercial."
    ),
    "appointments": (
        "Tu negocio trabaja con turnos o citas agendadas. "
        "Las consultas más frecuentes son: disponibilidad de turnos, precios por servicio, "  # noqa: E501
        "cobertura de obra social / prepaga, dirección y medios de pago. "
        "Cuando un cliente consulta disponibilidad de turno o quiere agendar, "
        "hay intención comercial."
    ),
    "real_estate": (
        "Trabajás en el rubro inmobiliario: venta o alquiler de propiedades. "
        "Las consultas más frecuentes son: propiedades disponibles, precios, "
        "condiciones de alquiler, requisitos y visitas. "
        "Cuando un cliente pide información sobre una propiedad específica o quiere "
        "coordinar una visita, hay intención comercial."
    ),
    "other": "",
}

# Lead threshold instructions embedded in the system prompt.
_LEAD_THRESHOLD_INSTRUCTIONS = {
    "any_inquiry": (
        "Registrá como lead a CUALQUIER persona que se contacte, incluso si solo hace "
        "una consulta general o pregunta básica. "
        "Desde el inicio de la conversación intentá obtener su nombre y número de teléfono "  # noqa: E501
        "de forma natural: por ejemplo '¿Me podés dejar tu nombre para personalizar la atención?'. "  # noqa: E501
        "Usá lead_temperature='warm' para cualquier contacto y siempre completá "
        "intent_signal con 'Cliente realizó una consulta' y next_action con 'Dar seguimiento'."  # noqa: E501
    ),
    "product_interest": (
        "Registrá como lead a los clientes que pregunten por el precio, disponibilidad "
        "o características de un producto o servicio específico. "
        "No registres consultas genéricas del tipo '¿qué vendés?' o '¿están abiertos?'. "  # noqa: E501
        "Antes de crear el lead, intentá obtener su nombre y número de contacto de forma natural: "  # noqa: E501
        "'Para pasarte la info detallada, ¿me decís tu nombre y un teléfono de contacto?'. "  # noqa: E501
        "Usá lead_temperature='warm' cuando pregunte por precio o producto, "
        "y 'hot' cuando pida avanzar o comprar."
    ),
    "clear_intent": (
        "Registrá como lead ÚNICAMENTE a los clientes que muestren intención clara de comprar "  # noqa: E501
        "o contratar: cuando pidan avanzar, confirmen que quieren el producto/servicio, "  # noqa: E501
        "pregunten por formas de pago o financiación, pidan una propuesta/presupuesto concreto, "  # noqa: E501
        "o quieran coordinar una visita/turno/prueba. "
        "NO crees leads por consultas generales, preguntas sobre horarios, precios genéricos "  # noqa: E501
        "o dudas informativas. Esperá la señal clara antes de actuar. "
        "Usá lead_temperature='hot' para estos casos."
    ),
}

_KB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_kb",
            "description": "Show the current list of knowledge base items",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_kb_item",
            "description": "View the processed content of a knowledge base item",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "1-based index in the list",
                    }
                },
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_kb_item",
            "description": "Remove a knowledge base item from the agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "1-based index in the list",
                    }
                },
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_file_upload",
            "description": "Ask the user to attach a new file to add to the knowledge base",  # noqa: E501
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_file_for_update",
            "description": "Ask the user to attach a file to replace an existing KB item",  # noqa: E501
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": "1-based index of the item to replace",
                    }
                },
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exit_kb",
            "description": "Exit KB management mode when user is done",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "respond",
            "description": "Send an informational response to the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Response text"}
                },
                "required": ["message"],
            },
        },
    },
]

_DONE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_kb",
            "description": (
                "Open knowledge base management when the user wants to add, view, "
                "edit, delete, upload, or manage files/documents/context for the agent"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_prompt",
            "description": (
                "Show the agent's current system prompt when the user asks to "
                "see, review or check the prompt or instructions"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_instructions",
            "description": (
                "Update the agent's extra/special instructions with new text "
                "provided by the user. Use when the user wants to add or change "
                "specific rules, restrictions or extra behaviour for the agent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "The new extra instructions to set on the agent",
                    }
                },
                "required": ["instructions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "respond",
            "description": "Reply to the user with an informational message",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Response text"}
                },
                "required": ["message"],
            },
        },
    },
]


class ChatroomAiAgentSetupSession(models.Model):
    _name = "chatroom.ai.agent.setup.session"
    _description = "AI Agent Setup Session (Discuss-based)"

    channel_id = fields.Many2one("discuss.channel", required=True, ondelete="cascade")
    step = fields.Selection(
        [
            ("business_name", "Business Name"),
            ("agent_name", "Agent Name"),
            ("business_type", "Business Type"),
            ("business_description", "Business Description"),
            ("objective", "Objective"),
            ("lead_threshold", "Lead Threshold"),
            ("tone", "Tone"),
            ("extra_instructions", "Extra Instructions"),
            ("confirm", "Confirm"),
            ("done", "Done"),
            ("kb_manage", "Manage Knowledge Base"),
            ("kb_awaiting_update", "Awaiting KB File Update"),
        ],
        default="business_name",
        required=True,
    )

    bot_partner_id = fields.Many2one("res.partner", readonly=True)

    # Mode: create new agent or update existing
    agent_id = fields.Many2one("chatroom.ai.agent", string="Agent to update")

    # Collected data
    business_name = fields.Char()
    agent_name = fields.Char(
        help="Custom name for the assistant persona (e.g. 'Lucas', 'Sofia'). "
        "If empty, the agent will introduce itself as the business assistant.",
    )
    business_type = fields.Selection(
        [
            ("distributor", "Distribuidora / Mayorista"),
            ("retail", "Comercio minorista"),
            ("automotive", "Automotriz / Motos / Vehículos"),
            ("services", "Servicios"),
            ("appointments", "Servicios con turnos"),
            ("real_estate", "Inmobiliaria / Propiedades"),
            ("other", "Otro"),
        ]
    )
    business_description = fields.Text()
    objective = fields.Selection(
        [
            ("leads", "Capture leads"),
            ("faq", "Answer FAQs"),
            ("both", "Both"),
        ]
    )
    lead_threshold = fields.Selection(
        [
            ("any_inquiry", "Cualquier consulta"),
            ("product_interest", "Precio o producto específico"),
            ("clear_intent", "Intención clara de comprar"),
        ]
    )
    tone = fields.Selection(
        [
            ("friendly", "Friendly"),
            ("formal", "Formal"),
            ("neutral", "Neutral"),
        ]
    )
    extra_instructions = fields.Text()
    generated_prompt = fields.Text()
    created_agent_id = fields.Many2one("chatroom.ai.agent", readonly=True)

    # KB management
    kb_pending_update_id = fields.Many2one(
        "chatroom.ai.knowledge", string="KB item pending update"
    )

    @api.model
    def action_start_setup(self, agent_id=None):
        bot = self._get_bot_partner()

        if agent_id:
            agent = self.env["chatroom.ai.agent"].browse(agent_id)
            channel_name = f"Setup: {agent.name}"
            greeting = (
                f"Vamos a re-configurar el agente **{agent.name}**. 🔄\n\n"
                "¿Cuál es el nombre del negocio?"
            )
        else:
            channel_name = "New Agent Setup"
            greeting = (
                "¡Hola! Voy a ayudarte a configurar tu agente de IA "
                "en unos pasos simples. 🚀\n\n"
                "¿Cuál es el nombre de tu negocio?"
            )

        channel = (
            self.env["discuss.channel"]
            .sudo()
            .create(
                {
                    "name": channel_name,
                    "channel_type": "group",
                    "channel_member_ids": [
                        (0, 0, {"partner_id": self.env.user.partner_id.id}),
                        (0, 0, {"partner_id": bot.id}),
                    ],
                }
            )
        )

        session = self.create(
            {
                "channel_id": channel.id,
                "bot_partner_id": bot.id,
                "agent_id": agent_id or False,
                "step": "business_name",
            }
        )

        # Link back so the channel hook can find the session
        channel.sudo().write({"setup_session_id": session.id})

        session._bot_post(greeting)

        return {
            "type": "ir.actions.client",
            "tag": "mail.action_discuss",
            "params": {"active_id": f"discuss.channel_{channel.id}"},
        }

    def process_user_message(self, text):  # noqa: C901
        self.ensure_one()
        text = text.strip()

        if self.step == "business_name":
            if not text:
                self._bot_post("Por favor escribí el nombre de tu negocio.")
                return
            self.business_name = text
            self.step = "agent_name"
            self._bot_post(
                f"Perfecto, **{text}**! 🎉\n\n"
                "¿Con qué nombre quiero que se presente el asistente a los clientes?\n\n"  # noqa: E501
                "Por ejemplo: _Lucas_, _Sofía_, _Max_.\n\n"
                "Si no querés un nombre personalizado, escribí **ninguno** y lo llamaremos "  # noqa: E501
                f"'Asistente de {text}'."
            )

        elif self.step == "agent_name":
            t = text.lower().strip()
            if t in ("ninguno", "no", "skip", "-", "nada", "ninguna", "sin nombre"):
                self.agent_name = False
            else:
                self.agent_name = text.strip()
            self.step = "business_type"
            self._bot_post(
                "¿A qué tipo de negocio pertenecés?" + _BUSINESS_TYPE_OPTIONS
            )

        elif self.step == "business_type":
            business_type = self._parse_business_type(text)
            if not business_type:
                self._bot_post(
                    "No entendí. Por favor elegí una opción:" + _BUSINESS_TYPE_OPTIONS
                )
                return
            self.business_type = business_type
            self.step = "business_description"
            self._bot_post(
                "¿Qué vendés o qué servicios ofrecés? Describilo brevemente."
            )

        elif self.step == "business_description":
            if not text:
                self._bot_post("Por favor describí brevemente tu negocio o servicios.")
                return
            self.business_description = text
            self.step = "objective"
            self._bot_post(
                "¿Cuál es el objetivo principal del agente?" + _OBJECTIVE_OPTIONS
            )

        elif self.step == "objective":
            objective = self._parse_objective(text)
            if not objective:
                self._bot_post(
                    "No entendí. Por favor elegí una opción:" + _OBJECTIVE_OPTIONS
                )
                return
            self.objective = objective
            if objective in ("leads", "both"):
                self.step = "lead_threshold"
                self._bot_post(
                    "¿Cuándo querés que el agente registre una consulta como posible cliente?"  # noqa: E501
                    + _LEAD_THRESHOLD_OPTIONS
                )
            else:
                self.step = "tone"
                self._bot_post("¿Qué tono querés que use el agente?" + _TONE_OPTIONS)

        elif self.step == "lead_threshold":
            threshold = self._parse_lead_threshold(text)
            if not threshold:
                self._bot_post(
                    "No entendí. Por favor elegí una opción:" + _LEAD_THRESHOLD_OPTIONS
                )
                return
            self.lead_threshold = threshold
            self.step = "tone"
            self._bot_post("¿Qué tono querés que use el agente?" + _TONE_OPTIONS)

        elif self.step == "tone":
            tone = self._parse_tone(text)
            if not tone:
                self._bot_post(
                    "No entendí. Por favor elegí una opción:" + _TONE_OPTIONS
                )
                return
            self.tone = tone
            self.step = "extra_instructions"
            self._bot_post(
                "¿Hay alguna instrucción extra o restricción importante para el agente? "  # noqa: E501
                "(Ej: horarios de atención, preguntas que no debe responder, datos de contacto)\n\n"  # noqa: E501
                "Escribí las instrucciones o **ninguna** para saltear."
            )

        elif self.step == "extra_instructions":
            if text.lower() not in (
                "ninguna",
                "no",
                "skip",
                "n",
                "-",
                "nada",
                "ninguno",
            ):
                self.extra_instructions = text
            else:
                self.extra_instructions = False

            obj_label = {
                "leads": "Capturar leads",
                "faq": "Responder FAQs",
                "both": "Ambos",
            }
            tone_label = {
                "friendly": "Amigable",
                "formal": "Formal",
                "neutral": "Neutral",
            }
            btype_label = _BUSINESS_TYPE_LABELS.get(self.business_type or "", "")
            threshold_label = _LEAD_THRESHOLD_LABELS.get(self.lead_threshold or "", "")
            summary = (
                f"📋 **Resumen del agente:**\n• **Negocio:** {self.business_name}\n"
            )
            if self.agent_name:
                summary += f"• **Nombre del asistente:** {self.agent_name}\n"
            if btype_label:
                summary += f"• **Tipo de negocio:** {btype_label}\n"
            summary += f"• **Descripción:** {self.business_description}\n"
            summary += (
                f"• **Objetivo:** {obj_label.get(self.objective, self.objective)}\n"
            )
            if threshold_label:
                summary += f"• **Capturar lead cuando:** {threshold_label}\n"
            summary += f"• **Tono:** {tone_label.get(self.tone, self.tone)}\n"
            if self.extra_instructions:
                summary += f"• **Instrucciones extra:** {self.extra_instructions}\n"

            is_update = bool(self.agent_id)
            verb = "actualizar el agente" if is_update else "crear el agente"
            summary += f"\n¿{verb.capitalize()}? Escribí **sí** para confirmar o **no** para empezar de nuevo."  # noqa: E501
            self.step = "confirm"
            self._bot_post(summary)

        elif self.step == "confirm":
            if text.lower() in (
                "sí",
                "si",
                "s",
                "yes",
                "ok",
                "dale",
                "confirmar",
                "confirmo",
                "crear",
            ):
                self._create_agent()
            elif text.lower() in ("no", "cancelar", "cancel", "reiniciar"):
                self.step = "business_name"
                self.business_name = False
                self.agent_name = False
                self.business_type = False
                self.business_description = False
                self.objective = False
                self.lead_threshold = False
                self.tone = False
                self.extra_instructions = False
                self._bot_post(
                    "Entendido, volvamos a empezar. ¿Cuál es el nombre de tu negocio?"
                )
            else:
                self._bot_post(
                    "Escribí **sí** para confirmar o **no** para empezar de nuevo."
                )

        elif self.step == "done":
            self._done_process_with_llm(text)

        elif self.step == "kb_manage":
            self._kb_process_with_llm(text)

        elif self.step == "kb_awaiting_update":
            t = text.lower().strip()
            if t in ("cancelar", "cancel", "volver", "back"):
                self.kb_pending_update_id = False
                self.step = "kb_manage"
                agent = self._kb_get_agent()
                self._bot_post("Actualización cancelada.")
                self._kb_list_post(agent)
            else:
                kb = self.kb_pending_update_id
                name = kb.name if kb else "el archivo"
                self._bot_post(f"Adjuntá el nuevo archivo para reemplazar **{name}**.")

    def _create_agent(self):
        provider = self.env["chatroom.ai.provider"].search(
            [("state", "=", "active")], limit=1
        )
        if not provider:
            self._bot_post(
                "⚠️ No hay proveedores de IA activos. "
                "Por favor configurá uno en **AI Agents → AI Providers** y volvé a intentarlo."  # noqa: E501
            )
            return

        self.generated_prompt = self._build_prompt()

        tool_ids = []
        if self.objective in ("leads", "both"):
            lead_tools = self.env["chatroom.ai.tool"].search(
                [("code_name", "in", ["create_lead", "update_lead"])]
            )
            tool_ids = [(4, t.id) for t in lead_tools]

        is_update = bool(self.agent_id)
        agent_display_name = (
            self.agent_name
            or (self.agent_id.name if is_update else None)
            or f"Asistente de {self.business_name}"
        )
        if is_update:
            self.agent_id.write(
                {
                    "provider_id": provider.id,
                    "system_prompt": self.generated_prompt,
                    "tool_ids": [(5, 0, 0)] + tool_ids,
                }
            )
            result_agent = self.agent_id
            verb = "actualizado"
        else:
            result_agent = self.env["chatroom.ai.agent"].create(
                {
                    "name": agent_display_name,
                    "provider_id": provider.id,
                    "system_prompt": self.generated_prompt,
                    "unsupported_media_message": (
                        "Lo siento, no puedo procesar archivos multimedia. "
                        "Por favor escribime tu consulta en texto."
                    ),
                    "tool_ids": tool_ids,
                }
            )
            verb = "creado"

        self.created_agent_id = result_agent
        self.step = "done"
        agent_link = self._agent_link(result_agent)
        self._bot_post_html(
            Markup(
                f"🎉 ¡Agente <strong>{result_agent.name}</strong> {verb} exitosamente!<br/><br/>"  # noqa: E501
                f"Proveedor asignado: <strong>{provider.name}</strong><br/><br/>"
                f"Ver agente: {agent_link}<br/><br/>"
                "¿Querés cargar documentos al knowledge base?"
            )
        )

    @staticmethod
    def _parse_objective(text):
        t = text.lower().strip()
        if t in ("1", "leads", "lead", "capturar"):
            return "leads"
        if t in ("2", "faq", "preguntas", "frecuentes", "responder"):
            return "faq"
        if t in ("3", "ambos", "both", "todo", "los dos"):
            return "both"
        return None

    @staticmethod
    def _parse_tone(text):
        t = text.lower().strip()
        if t in ("1", "amigable", "friendly", "cercano"):
            return "friendly"
        if t in ("2", "formal", "profesional"):
            return "formal"
        if t in ("3", "neutral", "directo"):
            return "neutral"
        return None

    @staticmethod
    def _parse_business_type(text):
        t = text.lower().strip()
        if t in ("1", "distribuidora", "mayorista", "distribuidor", "distributor"):
            return "distributor"
        if t in ("2", "retail", "minorista", "tienda", "local", "comercio"):
            return "retail"
        if t in (
            "3",
            "automotriz",
            "motos",
            "moto",
            "vehiculos",
            "autos",
            "automotive",
        ):
            return "automotive"
        if t in ("4", "servicios", "services", "reparaciones", "instalaciones"):
            return "services"
        if t in (
            "5",
            "turnos",
            "appointments",
            "medico",
            "médico",
            "dentista",
            "peluqueria",
        ):
            return "appointments"
        if t in ("6", "inmobiliaria", "propiedades", "real_estate", "inmuebles"):
            return "real_estate"
        if t in ("7", "otro", "other", "ninguno"):
            return "other"
        # Fuzzy matching for free-text input
        if any(w in t for w in ("distribu", "mayor")):
            return "distributor"
        if any(w in t for w in ("moto", "auto", "vehic", "carro", "repuest")):
            return "automotive"
        if any(
            w in t
            for w in ("turno", "cita", "agenda", "médic", "medic", "denti", "peluc")
        ):
            return "appointments"
        if any(w in t for w in ("inmob", "propied", "alquil", "depart")):
            return "real_estate"
        if any(w in t for w in ("servic", "repar", "instal", "limpi", "manten")):
            return "services"
        if any(w in t for w in ("tienda", "retail", "comerci", "ropa", "calzado")):
            return "retail"
        return None

    @staticmethod
    def _parse_lead_threshold(text):
        t = text.lower().strip()
        if t in ("1", "cualquier", "todo", "todos", "capturar todo", "any"):
            return "any_inquiry"
        if t in ("2", "precio", "producto", "interes", "interés", "product"):
            return "product_interest"
        if t in (
            "3",
            "intencion",
            "intención",
            "clara",
            "clear",
            "comprar",
            "contratar",
        ):
            return "clear_intent"
        # Fuzzy matching
        if any(w in t for w in ("cualquier", "todo contact", "captura max")):
            return "any_inquiry"
        if any(w in t for w in ("precio", "producto", "específico", "especific")):
            return "product_interest"
        if any(w in t for w in ("intent", "comprar", "contrat", "claro", "clara")):
            return "clear_intent"
        return None

    @api.model
    def _get_bot_partner(self):
        partner = (
            self.env["res.partner"]
            .sudo()
            .search(
                [("name", "=", "Setup Assistant"), ("active", "in", [True, False])],
                limit=1,
            )
        )
        if not partner:
            partner = (
                self.env["res.partner"]
                .sudo()
                .create({"name": "Setup Assistant", "tz": "UTC"})
            )
        return partner

    def _done_process_with_llm(self, text):  # noqa: C901
        self.ensure_one()
        agent = self._kb_get_agent()

        provider = None
        if agent:
            provider = agent.sudo().provider_id
            if not provider or provider.state != "active":
                provider = None
        if not provider:
            provider = self.env["chatroom.ai.provider"].search(
                [("state", "=", "active")], limit=1
            )

        if not provider:
            self._bot_post(
                "El agente ya fue configurado. "
                "Podés pedirme gestionar los archivos del knowledge base."
            )
            return

        agent_name = agent.name if agent else "el agente"
        kb_count = len(agent.sudo().knowledge_ids) if agent else 0

        # Fetch last bot message to give the LLM conversation context
        last_bot_msg = self.env["mail.message"].search(
            [
                ("res_id", "=", self.channel_id.id),
                ("model", "=", "discuss.channel"),
                ("author_id", "=", self.bot_partner_id.id),
            ],
            order="id desc",
            limit=1,
        )

        last_bot_text = (
            re.sub(r"<[^>]+>", "", last_bot_msg.body or "").strip()
            if last_bot_msg
            else ""
        )

        system_prompt = (
            f"El agente '{agent_name}' ya fue configurado correctamente. "
            f"Tiene {kb_count} item(s) en el knowledge base.\n\n"
            "Si el usuario quiere ver, agregar, modificar, borrar o gestionar archivos/documentos "  # noqa: E501
            "del knowledge base → llamá open_kb.\n"
            "Si el usuario quiere ver, revisar o leer el prompt/instrucciones del agente "  # noqa: E501
            "→ llamá view_prompt.\n"
            "Si el usuario quiere agregar, cambiar o actualizar instrucciones especiales del agente "  # noqa: E501
            "→ llamá update_instructions con el nuevo texto.\n"
            "Para cualquier otra cosa → llamá respond con una respuesta útil."
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if last_bot_text:
            messages.append({"role": "assistant", "content": last_bot_text})
        messages.append({"role": "user", "content": text})

        try:
            result = provider.generate_completion(
                messages, tools=_DONE_TOOLS, max_tokens=200
            )
        except Exception as e:
            _logger.error("Done LLM routing failed: %s", e)
            self._bot_post(f"⚠️ Error al procesar: {e}")
            return

        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            content = result.get("content", "")
            if content:
                self._bot_post(content)
            return

        func_name = tool_calls[0]["function"]["name"]
        if func_name == "open_kb":
            if not agent:
                self._bot_post("⚠️ No hay agente configurado.")
                return
            self.step = "kb_manage"
            self._kb_list_post(agent)
        elif func_name == "view_prompt":
            if not agent:
                self._bot_post("⚠️ No hay agente configurado.")
                return
            prompt = agent.sudo().system_prompt or "(sin prompt)"
            self._bot_post(f"📋 **Prompt del agente {agent.name}:**\n\n{prompt}")
        elif func_name == "update_instructions":
            if not agent:
                self._bot_post("⚠️ No hay agente configurado.")
                return
            try:
                args = json.loads(tool_calls[0]["function"].get("arguments") or "{}")
            except (json.JSONDecodeError, ValueError):
                args = {}
            new_instructions = args.get("instructions", "").strip()
            if new_instructions:
                # Rebuild prompt with updated extra instructions
                self.extra_instructions = new_instructions
                new_prompt = self._build_prompt()
                agent.sudo().write({"system_prompt": new_prompt})
                self.generated_prompt = new_prompt
                self._bot_post(
                    f"✅ Instrucciones especiales actualizadas en el agente **{agent.name}**. "  # noqa: E501
                    "El prompt fue regenerado."
                )
            else:
                self._bot_post(
                    "No pude extraer las instrucciones. Por favor escribilas de nuevo."
                )
        elif func_name == "respond":
            try:
                args = json.loads(tool_calls[0]["function"].get("arguments") or "{}")
            except (json.JSONDecodeError, ValueError):
                args = {}
            msg = args.get("message", result.get("content", ""))
            if msg:
                self._bot_post(msg)

    def _kb_get_agent(self):
        return self.created_agent_id or self.agent_id

    def _kb_process_with_llm(self, text):
        self.ensure_one()
        agent = self._kb_get_agent()
        if not agent:
            self._bot_post("⚠️ No hay agente asociado.")
            return

        provider = agent.sudo().provider_id
        if not provider or provider.state != "active":
            provider = self.env["chatroom.ai.provider"].search(
                [("state", "=", "active")], limit=1
            )

        if not provider:
            self._bot_post(
                "⚠️ No hay proveedor de IA activo para interpretar el comando."
            )
            return

        items = list(agent.sudo().knowledge_ids)
        if items:
            kb_summary = "\n".join(
                f"{i + 1}. {kb.name} | tipo: {kb.content_type} | "
                f"estado: {kb.processing_status} | {kb.char_count:,} chars"
                for i, kb in enumerate(items)
            )
        else:
            kb_summary = "(sin items)"

        system_prompt = (
            f"Sos el asistente de gestión del knowledge base del agente '{agent.name}'.\n\n"  # noqa: E501
            f"Knowledge base actual:\n{kb_summary}\n\n"
            "Interpretá la solicitud del usuario y llamá a la herramienta correspondiente. "  # noqa: E501
            "Siempre llamá exactamente una herramienta. "
            "Usá los índices numéricos (1-based) para referenciar items. "
            "Si el usuario quiere salir/terminar/listo/volver/ver prompt/ver instrucciones/cambiar instrucciones → exit_kb. "  # noqa: E501
            "Si quiere ver la lista → list_kb. "
            "Si quiere ver el contenido de un item → view_kb_item. "
            "Si quiere eliminar/borrar un item → delete_kb_item. "
            "Si quiere subir un archivo nuevo → request_file_upload. "
            "Si quiere reemplazar/actualizar un item existente → request_file_for_update. "  # noqa: E501
            "Para respuestas informativas → respond."
        )

        # Include last bot message so the LLM can resolve ambiguous replies like "sí"
        last_bot_msg = self.env["mail.message"].search(
            [
                ("res_id", "=", self.channel_id.id),
                ("model", "=", "discuss.channel"),
                ("author_id", "=", self.bot_partner_id.id),
            ],
            order="id desc",
            limit=1,
        )

        last_bot_text = (
            re.sub(r"<[^>]+>", "", last_bot_msg.body or "").strip()
            if last_bot_msg
            else ""
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if last_bot_text:
            messages.append({"role": "assistant", "content": last_bot_text})
        messages.append({"role": "user", "content": text})

        try:
            result = provider.generate_completion(
                messages, tools=_KB_TOOLS, max_tokens=300
            )
        except Exception as e:
            _logger.error("KB LLM processing failed: %s", e)
            self._bot_post(f"⚠️ Error al procesar con IA: {e}")
            return

        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            content = result.get("content", "")
            if content:
                self._bot_post(content)
            return

        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            try:
                args = json.loads(tool_call["function"].get("arguments") or "{}")
            except (json.JSONDecodeError, ValueError):
                args = {}
            self._kb_execute_tool(agent, items, func_name, args)

    def _kb_execute_tool(self, agent, items, func_name, args):
        if func_name == "list_kb":
            self._kb_list_post(agent)

        elif func_name == "view_kb_item":
            idx = args.get("index", 1) - 1
            if 0 <= idx < len(items):
                self._kb_view_post(items[idx])
            else:
                self._bot_post(f"⚠️ No encontré el item #{args.get('index')}.")

        elif func_name == "delete_kb_item":
            idx = args.get("index", 1) - 1
            if 0 <= idx < len(items):
                kb = items[idx]
                name = kb.name
                agent.sudo().write({"knowledge_ids": [(3, kb.id)]})
                self._bot_post(f"🗑️ **{name}** eliminado.")
                self._kb_list_post(agent)
            else:
                self._bot_post(f"⚠️ No encontré el item #{args.get('index')}.")

        elif func_name == "request_file_for_update":
            idx = args.get("index", 1) - 1
            if 0 <= idx < len(items):
                kb = items[idx]
                self.kb_pending_update_id = kb
                self.step = "kb_awaiting_update"
                self._bot_post(
                    f"📎 Adjuntá el nuevo archivo para reemplazar **{kb.name}**."
                )
            else:
                self._bot_post(f"⚠️ No encontré el item #{args.get('index')}.")

        elif func_name == "request_file_upload":
            self._bot_post("📎 Adjuntá el archivo.")

        elif func_name == "exit_kb":
            self.step = "done"
            self._bot_post("¡Listo! Knowledge base actualizado. 👍")

        elif func_name == "respond":
            msg = args.get("message", "")
            if msg:
                self._bot_post(msg)

    def _kb_list_post(self, agent=None):
        if agent is None:
            agent = self._kb_get_agent()
        if not agent:
            return
        items = agent.sudo().knowledge_ids
        if not items:
            self._bot_post(
                f"📚 Knowledge Base de {agent.name}\n\nNo hay archivos cargados todavía."  # noqa: E501
            )
            return

        rows = Markup("")
        for i, kb in enumerate(items, start=1):
            if kb.processing_status == "success":
                icon = "\u2705"
            elif kb.processing_status == "error":
                icon = "\u26a0\ufe0f"
            else:
                icon = "\u23f3"
            chars = f", {kb.char_count:,} chars" if kb.char_count else ""
            rows += Markup(
                f"{i}. <strong>{kb.name}</strong> "
                f"({kb.content_type}{chars}) {icon}<br/>"
            )

        self._bot_post_html(
            Markup(
                f"<strong>\ud83d\udcda Knowledge Base de {agent.name}</strong><br/><br/>"  # noqa: E501
                f"{rows}"
            )
        )

    def _kb_view_post(self, kb):
        content = (kb.sudo().processed_content or kb.sudo().content or "").strip()
        if not content:
            self._bot_post(f"**{kb.name}** no tiene contenido procesado aún.")
            return
        max_len = 1500
        truncated = Markup("")
        if len(content) > max_len:
            content = content[:max_len]
            truncated = Markup("<br/><em>...(contenido truncado)</em>")
        # Escape the content before marking as safe
        from markupsafe import escape

        self._bot_post_html(
            Markup(f"<strong>\ud83d\udcc4 {kb.name}</strong><br/><br/>")
            + escape(content).replace("\n", Markup("<br/>"))
            + truncated
        )

    def process_user_attachment(self, message):
        self.ensure_one()
        agent = self._kb_get_agent()
        if not agent:
            self._bot_post("⚠️ No hay agente asociado.")
            return

        for attachment in message.sudo().attachment_ids:
            if self.step == "kb_awaiting_update" and self.kb_pending_update_id:
                kb = self.kb_pending_update_id
                kb.sudo().write(
                    {
                        "file": attachment.datas,
                        "file_name": attachment.name,
                        "content_type": "file",
                        "processing_status": "not_processed",
                        "processed_content": False,
                    }
                )
                kb.sudo().action_process_content()
                status = "✅" if kb.processing_status == "success" else "⚠️"
                self._bot_post(
                    f"{status} **{kb.name}** actualizado con **{attachment.name}**"
                    + (f" ({kb.char_count:,} chars)" if kb.char_count else "")
                    + "."
                )
                self.kb_pending_update_id = False
                self.step = "kb_manage"
            else:
                kb = (
                    self.env["chatroom.ai.knowledge"]
                    .sudo()
                    .create(
                        {
                            "name": attachment.name,
                            "content_type": "file",
                            "file": attachment.datas,
                            "file_name": attachment.name,
                        }
                    )
                )
                kb.sudo().action_process_content()
                agent.sudo().write({"knowledge_ids": [(4, kb.id)]})
                status = "✅" if kb.processing_status == "success" else "⚠️"
                self._bot_post(
                    f"{status} **{attachment.name}** agregado al knowledge base"
                    + (f" ({kb.char_count:,} chars)" if kb.char_count else "")
                    + "."
                )

        self._kb_list_post(agent)

    def _agent_link(self, agent):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        action = self.env.ref("chatroom_ai.action_chatroom_ai_agent")
        url = f"{base_url}/odoo/action-{action.id}/{agent.id}"
        return Markup(f'<a href="{url}">{agent.name}</a>')

    def _bot_post_html(self, html_body):
        self.ensure_one()
        self.channel_id.sudo().message_post(
            body=html_body,
            author_id=self.bot_partner_id.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _bot_post(self, text):
        self.ensure_one()
        html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
        html = html.replace("\n", "<br/>")
        self.channel_id.sudo().message_post(
            body=Markup(html),
            author_id=self.bot_partner_id.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _build_prompt(self):
        business_name = self.business_name or "el negocio"

        if self.agent_name:
            identity_line = (
                f"Te llamás **{self.agent_name}** y sos el asistente virtual de "
                f"**{business_name}**."
            )
        else:
            identity_line = f"Sos el asistente virtual de **{business_name}**."

        tone_text = _TONE_TEXTS.get(self.tone, "neutral y directo")
        objective_text = _OBJECTIVE_TEXTS.get(self.objective, "")
        business_context = _BUSINESS_TYPE_CONTEXTS.get(
            self.business_type or "other", ""
        )

        context_section = f"\n{business_context}" if business_context else ""

        lead_section = ""
        if self.objective in ("leads", "both"):
            threshold_text = _LEAD_THRESHOLD_INSTRUCTIONS.get(
                self.lead_threshold or "product_interest", ""
            )
            contact_ask = (
                "\n\n**Cómo pedir los datos de contacto:**\n"
                "Pedí el nombre y número de forma natural, integrado en la conversación, "  # noqa: E501
                "nunca de manera abrupta ni como formulario. "
                "Ejemplos: '¿Me dejás tu nombre para personalizar la atención?', "
                "'Para mandarte la información, ¿me pasás un número de WhatsApp o email?'. "  # noqa: E501
                "Si el cliente no quiere dar datos, respetalo con amabilidad y seguí ayudándolo."  # noqa: E501
            )
            lead_section = (
                "\n\n## Registro de clientes potenciales\n"
                f"{threshold_text}{contact_ask}"
            )

        kb_section = ""
        if self.objective in ("faq", "both"):
            kb_section = (
                "\n\n## Uso del knowledge base\n"
                "Tenés documentos con información específica del negocio. "
                "Usá esa información como tu fuente primaria de respuestas. "
                "**Nunca inventes** datos, precios, productos o servicios que no figuran en los documentos. "  # noqa: E501
                "Si no encontrás la respuesta, decí claramente: "
                f"'No tengo esa información disponible. Te recomiendo consultarlo directamente con el equipo de {business_name}.'"  # noqa: E501
            )

        extra = (
            f"\n\n## Instrucciones especiales del negocio\n{self.extra_instructions}"
            if self.extra_instructions
            else ""
        )

        return (
            f"## Identidad\n"
            f"{identity_line}\n\n"
            f"## El negocio\n"
            f"{self.business_description}"
            f"{context_section}\n\n"
            f"## Tu objetivo\n"
            f"Tu objetivo principal es {objective_text}.\n\n"
            f"## Reglas de comportamiento\n"
            f"- **Idioma**: Respondé siempre en el mismo idioma en que te escribe el cliente.\n"  # noqa: E501
            f"- **Brevedad**: Máximo 3-4 oraciones por respuesta. "
            f"Usá listas cortas con viñetas cuando necesitás dar mucha información.\n"
            f"- **Honestidad**: Nunca inventes precios, stock, fechas ni información que no tenés. "  # noqa: E501
            f"Reconocé con claridad cuando no sabés algo.\n"
            f"- **Identidad**: Si te preguntan si sos un bot o IA, confirmalo con naturalidad. "  # noqa: E501
            f"Nunca finjas ser humano.\n"
            f"- **Confidencialidad**: No compartas datos de otros clientes ni "
            f"información interna del sistema.\n"
            f"- **Foco**: Respondé solo consultas relacionadas con {business_name}. "
            f"Para temas no relacionados, decí: "
            f"'Eso está fuera de lo que puedo ayudarte hoy. "
            f"¿Hay algo sobre {business_name} en lo que te pueda ayudar?'\n"
            f"- **Trato agresivo**: Si el cliente usa lenguaje agresivo o inapropiado, "
            f"respondé con calma y profesionalismo, sin devolver la agresión.\n\n"
            f"## Tono y estilo\n"
            f"{tone_text}\n\n"
            f"## Cuándo derivar al equipo humano\n"
            f"Derivá a un agente humano cuando:\n"
            f"- El cliente pide explícitamente hablar con una persona\n"
            f"- Tiene un reclamo formal o está muy insatisfecho con el servicio\n"
            f"- La consulta requiere una acción que vos no podés realizar "
            f"(ej: confirmar una reserva, autorizar un pago, resolver un problema técnico complejo)\n"  # noqa: E501
            f"Cuando derives, decí: 'Entendido. Voy a pedirle a nuestro equipo que te contacte. "  # noqa: E501
            f"¿Podés dejarme tu nombre y el mejor momento para que te llamen?'"
            f"{lead_section}"
            f"{kb_section}"
            f"{extra}"
        )

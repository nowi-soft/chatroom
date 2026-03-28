import json
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ChatroomAIAgent(models.Model):
    _name = "chatroom.ai.agent"
    _description = "AI Agent Configuration"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    provider_id = fields.Many2one(
        "chatroom.ai.provider",
        string="AI Provider",
        required=True,
        domain=[("state", "=", "active")],
    )
    model = fields.Char(
        string="Model Override",
        help="Leave empty to use provider's default model",
    )
    temperature = fields.Float(
        help="Leave 0 to use provider's default",
    )
    max_tokens = fields.Integer(
        help="Leave 0 to use provider's default, min 500",
    )

    @api.constrains("max_tokens")
    def _check_max_tokens(self):
        for record in self:
            if record.max_tokens < 0:
                raise ValidationError(self.env._("Max tokens cannot be negative."))
            if 0 < record.max_tokens < 500:
                raise ValidationError(
                    self.env._(
                        "Max tokens must be at least 500 or 0 to use provider default."
                    )
                )

    system_prompt = fields.Text(
        required=True,
        default="""
    You are a human-like sales assistant for a Honda dealership in Mendoza.

Conversation rules:
- Sound natural, warm, and concise.
- Ask only one simple question per turn.
- If user says only hello, greet naturally and ask an open help question
    (for example: "En que te puedo ayudar hoy?").
- Do not force product-category questions in the first turn
    (avoid "moto o cuatriciclo?" as default opener).
- Do not send long questionnaires.
- Ask only actionable questions that lead to an immediate next step.
- Do not ask for preferred contact time by default.
- Only ask preferred contact time if the customer offers it
    or if a real handoff is blocked without it.
- If channel metadata already identifies contact (e.g., WhatsApp),
    avoid asking phone again unless strictly required.
- Do not mention AI, tools, internal processes, lead IDs, or backend actions.
- Mentally classify lead temperature in each turn: cold, warm, hot.

Sales flow:
- Understand the need first, then recommend.
- Mention financing/test ride only when relevant.
- Use create_lead only with clear commercial intent.
- Never create a lead when temperature is cold.
- Create/update lead when warm/hot and there is
    actionable contact/progression data.
- After creating/updating a lead, confirm briefly and close naturally
    without adding extra questions unless a critical contact datum is missing.

Always maintain conversation context from previous messages.
""",
        help="Core instructions that define the agent's behavior and personality",
    )

    knowledge_ids = fields.Many2many(
        "chatroom.ai.knowledge",
        "chatroom_ai_agent_knowledge_rel",
        "agent_id",
        "knowledge_id",
        "Knowledge Base",
        help="Documents and information the agent can use to answer questions",
    )

    tool_ids = fields.Many2many(
        "chatroom.ai.tool",
        "chatroom_ai_agent_tool_rel",
        "agent_id",
        "tool_id",
        "Available Tools",
        help="Actions the agent can perform (create leads, send emails, etc.)",
    )

    max_conversation_length = fields.Integer(
        "Max Conversation Messages",
        default=20,
        help=(
            "Maximum number of messages to include in context "
            "(older messages are summarized)"
        ),
    )

    unsupported_media_message = fields.Text(
        default=(
            "I'm sorry, but I cannot process images, files, or videos "
            "at this time. Please describe what you need in text, and "
            "I'll be happy to help you."
        ),
        help=(
            "Message sent when the agent receives an image, file, or "
            "video that it cannot process"
        ),
        required=True,
    )

    total_responses = fields.Integer(default=0, readonly=True)
    total_tool_executions = fields.Integer(default=0, readonly=True)
    last_response_date = fields.Datetime(string="Last Response", readonly=True)

    conversation_ids = fields.One2many(
        "chatroom.ai.conversation",
        "agent_id",
        string="Conversations",
    )
    conversation_count = fields.Integer(
        compute="_compute_conversation_count",
        string="Conversations",
    )

    @api.depends("conversation_ids")
    def _compute_conversation_count(self):
        for agent in self:
            agent.conversation_count = len(agent.conversation_ids)

    def action_view_conversations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Agent Conversations",
            "res_model": "chatroom.ai.conversation",
            "view_mode": "list,form",
            "domain": [("agent_id", "=", self.id)],
            "context": {
                "default_agent_id": self.id,
                "search_default_active": 1,
            },
        }

    def should_respond_to_room(self, room):
        self.ensure_one()

        if not self.active:
            return False

        return not room.assigned_to_id

    def get_or_create_conversation(self, room):
        self.ensure_one()

        conversation = self.env["chatroom.ai.conversation"].search(
            [
                ("agent_id", "=", self.id),
                ("room_id", "=", room.id),
                ("state", "=", "active"),
            ],
            limit=1,
        )

        if not conversation:
            conversation = self.env["chatroom.ai.conversation"].create(
                {
                    "agent_id": self.id,
                    "room_id": room.id,
                    "state": "active",
                }
            )

        return conversation

    def _transcribe_audio(self, message):
        self.ensure_one()

        if not message.attachment_id and not message.file_url:
            return None

        try:
            if hasattr(self.provider_id, "transcribe_audio"):
                if message.attachment_id:
                    audio_data = message.attachment_id.datas
                    mime_type = message.mime_type or message.attachment_id.mimetype

                    transcription = self.provider_id.transcribe_audio(
                        audio_data=audio_data,
                        mime_type=mime_type,
                    )
                    return transcription
                elif message.file_url:
                    response = requests.get(message.file_url, timeout=30)
                    if response.status_code == 200:
                        audio_data = response.content
                        transcription = self.provider_id.transcribe_audio(
                            audio_data=audio_data,
                            mime_type=message.mime_type or "audio/ogg",
                        )
                        return transcription
            else:
                return self.env._(
                    "[Audio message received - transcription not available]"
                )

        except Exception:
            return None

        return None

    def _generate_and_send_response(self, conversation_id):
        conversation = self.env["chatroom.ai.conversation"].browse(conversation_id)
        if not conversation.exists():
            return

        agent = conversation.agent_id
        room = conversation.room_id

        try:
            context_messages = conversation.build_context_messages()

            tools = None
            if agent.tool_ids:
                tools = [
                    agent.provider_id.format_tool_for_provider(tool)
                    for tool in agent.tool_ids
                ]

            result = agent.provider_id.generate_completion(
                messages=context_messages,
                model=agent.model or None,
                temperature=agent.temperature or None,
                max_tokens=agent.max_tokens or None,
                tools=tools,
            )

            has_content = bool((result or {}).get("content"))
            has_tool_calls = bool((result or {}).get("tool_calls"))

            if not result or (not has_content and not has_tool_calls):
                _logger.error(
                    f"AI response empty or invalid for room {room.name}. "
                    f"Result: {result}, "
                    f"Has content: {has_content}, "
                    f"Has tool calls: {has_tool_calls}"
                )
                room.action_pause_ai_and_request_attention()
                return

            if result.get("tool_calls"):
                conversation.add_assistant_message_with_tools(
                    content=result.get("content"), tool_calls=result.get("tool_calls")
                )

                tool_results = []
                for tool_call in result["tool_calls"]:
                    tool_result = agent._execute_tool_call(conversation, tool_call)
                    tool_results.append(
                        {
                            "id": tool_call.get("id"),
                            "name": tool_call.get("name"),
                            "result": tool_result,
                        }
                    )

                conversation.add_tool_results(tool_results)

                result = agent.provider_id.generate_completion(
                    messages=conversation.build_context_messages(),
                    model=agent.model or None,
                    temperature=agent.temperature or None,
                    max_tokens=agent.max_tokens or None,
                )

            if not result.get("content"):
                return

            message_vals = {
                "room_id": room.id,
                "body": result["content"],
                "direction": "outgoing",
                "user_id": self.env.ref("base.user_admin").id,
                "author_name": agent.name,
                "is_ai_generated": True,
            }

            ai_message = self.env["chatroom.message"].sudo().create(message_vals)

            conversation.add_message(ai_message)

            agent.sudo().write(
                {
                    "total_responses": agent.total_responses + 1,
                    "last_response_date": fields.Datetime.now(),
                }
            )

        except Exception as e:
            _logger.error(f"Error generating AI response: {str(e)}")
            conversation.write({"state": "error", "error_message": str(e)})
            room.action_pause_ai_and_request_attention()

    def _execute_tool_call(self, conversation, tool_call):
        self.ensure_one()

        if "function" in tool_call:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"].get("arguments", {})
        else:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})

        tool_call_id = tool_call.get("id")

        if tool_call_id and conversation.has_tool_call_result(tool_call_id):
            existing_result = conversation.get_tool_call_result(tool_call_id)
            _logger.info(
                "Skipping duplicate tool_call_id %s for tool %s in conversation %s",
                tool_call_id,
                tool_name,
                conversation.id,
            )
            return existing_result

        if isinstance(tool_args, str):
            try:
                parsed_args = json.loads(tool_args)
                if isinstance(parsed_args, dict):
                    tool_args = parsed_args
                else:
                    _logger.warning(
                        "Tool %s arguments parsed to non-dict (%s). Using empty args.",
                        tool_name,
                        type(parsed_args).__name__,
                    )
                    tool_args = {}
            except (json.JSONDecodeError, ValueError) as e:
                _logger.warning(
                    (
                        "Invalid JSON arguments for tool %s. "
                        "Using empty args. Raw: %s Error: %s"
                    ),
                    tool_name,
                    tool_args,
                    e,
                )
                tool_args = {}
        elif not isinstance(tool_args, dict):
            _logger.warning(
                "Tool %s received non-dict arguments (%s). Using empty args.",
                tool_name,
                type(tool_args).__name__,
            )
            tool_args = {}

        tool = self.tool_ids.filtered(lambda t: t.code_name == tool_name)
        if not tool:
            _logger.warning(f"Tool {tool_name} not found for agent {self.name}")
            return {"error": f"Tool {tool_name} not found"}

        try:
            result = tool.execute(conversation.room_id, tool_args, conversation)

            _logger.info(
                "AI Tool '%s' executed - Parameters: %s - Result: %s",
                tool.name,
                json.dumps(tool_args, ensure_ascii=False),
                (
                    json.dumps(result, ensure_ascii=False)
                    if isinstance(result, dict)
                    else result
                ),
            )

            if isinstance(result, dict) and result.get("skipped"):
                tool_note = self.env._("🤖 AI Tool Skipped: %s ⏭️", tool.name)
            elif isinstance(result, dict) and (
                result.get("error") or result.get("success") is False
            ):
                tool_note = self.env._("🤖 AI Tool Failed: %s ❌", tool.name)
            else:
                tool_note = self.env._("🤖 AI Tool Executed: %s ✅", tool.name)

            self.env["chatroom.message"].create(
                {
                    "room_id": conversation.room_id.id,
                    "body": tool_note,
                    "direction": "outgoing",
                    "is_internal": True,
                    "user_id": self.env.ref("base.user_admin").id,
                }
            )

            self.sudo().write({"total_tool_executions": self.total_tool_executions + 1})

            return result

        except Exception as e:
            _logger.error(
                "Error executing tool %s - Parameters: %s - Error: %s",
                tool_name,
                json.dumps(tool_args, ensure_ascii=False),
                str(e),
            )

            self.env["chatroom.message"].create(
                {
                    "room_id": conversation.room_id.id,
                    "body": self.env._("🤖 AI Tool Failed: %s ❌", tool.name),
                    "direction": "outgoing",
                    "is_internal": True,
                    "user_id": self.env.ref("base.user_admin").id,
                }
            )

            return {"error": str(e)}

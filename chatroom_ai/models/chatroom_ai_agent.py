import json
import logging

import requests

from odoo import fields, models

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
    system_prompt = fields.Text(
        required=True,
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
        required=True,
        default="I'm sorry, I can only process text messages.",
        help=(
            "Message sent when the agent receives an image, file, or "
            "video that it cannot process"
        ),
    )

    def should_respond_to_room(self, room):
        self.ensure_one()

        if not self.active:
            return False

        return not room.assigned_to_id

    def action_open_setup_wizard(self):
        self.ensure_one()
        return self.env["chatroom.ai.agent.setup.session"].action_start_setup(
            agent_id=self.id
        )

    def get_or_create_conversation(self, room):
        self.ensure_one()
        if room.ai_conversation_state not in ("active", "testing"):
            room.write({"ai_conversation_state": "active"})
        return room

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

    @staticmethod
    def _convert_ai_response_to_html(text):
        if not text:
            return text
        import re

        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.DOTALL)
        text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
        lines = text.split("\n")
        deduped = []
        for line in lines:
            if deduped and line.strip() and line.strip() == deduped[-1].strip():
                continue
            deduped.append(line)
        text = "\n".join(deduped)
        text = text.replace("\n", "<br/>")
        return text

    def _generate_and_send_response(self, room_id):
        room = self.env["chatroom.room"].browse(room_id)
        if not room.exists():
            return

        agent = room.ai_agent_id or self

        try:
            context_messages = room.build_context_messages()

            tools = None
            if agent.tool_ids:
                tools = [
                    agent.provider_id.format_tool_for_provider(tool)
                    for tool in agent.tool_ids
                ]

            result = agent.provider_id.generate_completion(
                messages=context_messages,
                tools=tools,
            )

            has_content = bool((result or {}).get("content"))
            has_tool_calls = bool((result or {}).get("tool_calls"))

            if not result or (not has_content and not has_tool_calls):
                _logger.warning(
                    "AI response empty or invalid for room %s. "
                    "Result: %s, Has content: %s, Has tool calls: %s",
                    room.name,
                    result,
                    has_content,
                    has_tool_calls,
                )
                return

            if result.get("tool_calls"):
                room.add_assistant_message_with_tools(
                    content=result.get("content"), tool_calls=result.get("tool_calls")
                )

                tool_results = []
                for tool_call in result["tool_calls"]:
                    tool_result = agent._execute_tool_call(room, tool_call)
                    tool_results.append(
                        {
                            "id": tool_call.get("id"),
                            "name": tool_call.get("name"),
                            "result": tool_result,
                        }
                    )

                room.add_tool_results(tool_results)

                try:
                    result = agent.provider_id.generate_completion(
                        messages=room.build_context_messages(),
                    )
                except Exception as follow_up_error:
                    _logger.warning(
                        "Follow-up completion after tools failed for room %s: %s",
                        room.name,
                        follow_up_error,
                    )
                    return

            if not result.get("content"):
                return

            message_vals = {
                "room_id": room.id,
                "body": self._convert_ai_response_to_html(result["content"]),
                "direction": "outgoing",
                "user_id": self.env.ref("base.user_admin").id,
                "author_name": agent.name,
                "is_ai_generated": True,
            }

            ai_message = self.env["chatroom.message"].sudo().create(message_vals)

            room.add_message(ai_message)

        except Exception as e:
            _logger.error("Error generating AI response: %s", e)
            room.write({"ai_conversation_state": "error", "ai_error_message": str(e)})
            room.action_pause_ai_and_request_attention()

    def _execute_tool_call(self, room, tool_call):
        self.ensure_one()

        if "function" in tool_call:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"].get("arguments", {})
        else:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})

        tool_call_id = tool_call.get("id")

        if tool_call_id and room.has_tool_call_result(tool_call_id):
            existing_result = room.get_tool_call_result(tool_call_id)
            _logger.info(
                "Skipping duplicate tool_call_id %s for tool %s in room %s",
                tool_call_id,
                tool_name,
                room.id,
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
            _logger.warning("Tool %s not found for agent %s", tool_name, self.name)
            return {"error": f"Tool {tool_name} not found"}

        try:
            result = tool.execute(room, tool_args, room)

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
                    "room_id": room.id,
                    "body": tool_note,
                    "direction": "outgoing",
                    "is_internal": True,
                    "user_id": self.env.ref("base.user_admin").id,
                }
            )

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
                    "room_id": room.id,
                    "is_internal": True,
                    "user_id": self.env.ref("base.user_admin").id,
                }
            )

            return {"error": str(e)}

import json
import logging
from datetime import datetime

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ChatroomAIConversation(models.Model):
    _name = "chatroom.ai.conversation"
    _description = "AI Agent Conversation Context"
    _order = "create_date desc"

    agent_id = fields.Many2one(
        "chatroom.ai.agent", required=True, ondelete="cascade", index=True
    )
    room_id = fields.Many2one(
        "chatroom.room", required=True, ondelete="cascade", index=True
    )

    state = fields.Selection(
        [
            ("active", "Active"),
            ("paused", "Paused - Human Intervention"),
            ("completed", "Completed"),
            ("error", "Error"),
            ("testing", "Testing"),
        ],
        default="active",
        required=True,
    )

    context_messages = fields.Text(
        "Conversation Context (JSON)",
        help="Stored messages in OpenAI format for context",
    )
    summary = fields.Text(
        "Conversation Summary",
        help="AI-generated summary of older messages (for long conversations)",
    )

    message_count = fields.Integer(default=0)
    start_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    last_message_date = fields.Datetime()
    end_date = fields.Datetime()

    error_message = fields.Text()

    ai_responses = fields.Integer(default=0)
    human_messages = fields.Integer(default=0)
    tool_executions = fields.Integer(default=0)

    def _load_context(self):
        self.ensure_one()
        try:
            return json.loads(self.context_messages) if self.context_messages else []
        except (json.JSONDecodeError, ValueError) as e:
            _logger.warning("Failed to parse conversation context: %s", e)
            return []

    def has_tool_call_result(self, tool_call_id):
        self.ensure_one()
        if not tool_call_id:
            return False

        context = self._load_context()
        for msg in context:
            if msg.get("role") == "tool" and msg.get("tool_call_id") == tool_call_id:
                return True
        return False

    def get_tool_call_result(self, tool_call_id):
        self.ensure_one()
        if not tool_call_id:
            return None

        context = self._load_context()
        for msg in context:
            if msg.get("role") == "tool" and msg.get("tool_call_id") == tool_call_id:
                raw_content = msg.get("content")
                if isinstance(raw_content, dict):
                    return raw_content
                if isinstance(raw_content, str):
                    try:
                        return json.loads(raw_content)
                    except (json.JSONDecodeError, ValueError):
                        return {"raw": raw_content}
                return raw_content
        return None

    def _build_channel_context_block(self):
        self.ensure_one()

        room = self.room_id
        connector = room.connector_id
        connector_type = (
            (connector.connector_type or "unknown").lower() if connector else "unknown"
        )
        external_id = room.external_id or ""

        lines = ["=== CHANNEL CONTEXT ==="]
        lines.append(f"- Connector type: {connector_type}")
        if external_id:
            lines.append(f"- Channel external_id: {external_id}")

        # Channel-specific guidance to avoid redundant questions.
        if connector_type == "evolution":
            lines.append(
                "- External ID usually maps to WhatsApp phone. "
                "Avoid asking phone again unless strictly required."
            )
            lines.append(
                "- If needed, confirm contact data briefly "
                "instead of re-collecting from scratch."
            )
        elif connector_type == "telegram":
            lines.append(
                "- External ID is Telegram chat/user ID, not a guaranteed phone number."
            )
            lines.append(
                "- Ask for phone only if truly necessary for the next business action."
            )
        else:
            lines.append(
                "- Do not assume external_id is a phone number; "
                "validate contact data only when needed."
            )

        partner_names = []
        if hasattr(room, "partner_ids") and room.partner_ids:
            partner_names = [p.name for p in room.partner_ids if p.name]
        if partner_names:
            lines.append(f"- Linked contacts in Odoo: {', '.join(partner_names)}")

        lines.append(
            "- Keep questions minimal and action-oriented; "
            "avoid repeating data already available in metadata."
        )

        return "\n".join(lines)

    def add_message(self, message):
        self.ensure_one()

        context = self._load_context()

        role = "assistant" if message.direction == "outgoing" else "user"

        if message.is_internal:
            return

        existing_ids = [msg.get("message_id") for msg in context]
        if message.id in existing_ids:
            _logger.debug(
                "Message ID=%d already in context for conversation ID=%d",
                message.id,
                self.id,
            )
            return

        context.append(
            {
                "role": role,
                "content": message.body,
                "timestamp": message.create_date.isoformat()
                if message.create_date
                else None,
                "message_id": message.id,
            }
        )

        if role == "user":
            self.human_messages += 1
        else:
            self.ai_responses += 1

        max_length = self.agent_id.max_conversation_length or 20
        if len(context) > max_length:
            old_messages = context[:-max_length]
            context = context[-max_length:]

            self.summary = f"Previous {len(old_messages)} messages summarized."

        self.write(
            {
                "context_messages": json.dumps(context),
                "message_count": len(context),
                "last_message_date": fields.Datetime.now(),
            }
        )

    def build_context_messages(self):
        self.ensure_one()

        messages = []

        temporal_instructions = """IMPORTANT CONTEXT RULES:
- Each message below includes a timestamp [YYYY-MM-DD HH:MM:SS]
- This is an ongoing conversation - messages are historical context
- Do NOT greet the user again if you already greeted them in previous messages
- Only respond to the most recent message
- Reference previous context when relevant

"""

        channel_context = self._build_channel_context_block()

        system_content = (
            temporal_instructions
            + channel_context
            + "\n\n"
            + self.agent_id.system_prompt
        )

        if self.agent_id.knowledge_ids:
            knowledge_content = "\n\n=== KNOWLEDGE BASE ===\n\n"
            for knowledge in self.agent_id.knowledge_ids:
                knowledge_content += knowledge.get_formatted_content()
            system_content += "\n\n" + knowledge_content

        if self.summary:
            system_content += f"\n\n=== CONVERSATION SUMMARY ===\n{self.summary}\n"

        messages.append(
            {
                "role": "system",
                "content": system_content,
            }
        )

        try:
            context = self._load_context()
            for msg in context:
                content = msg.get("content", "")

                if msg.get("timestamp") and content and msg.get("role") == "user":
                    try:
                        ts = datetime.fromisoformat(msg["timestamp"])
                        time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                        content = f"[{time_str}] {content}"
                    except (ValueError, AttributeError) as e:
                        _logger.debug("Could not parse timestamp: %s", e)

                message = {
                    "role": msg["role"],
                    "content": content,
                }

                if "tool_calls" in msg:
                    message["tool_calls"] = msg["tool_calls"]

                if "tool_call_id" in msg:
                    message["tool_call_id"] = msg["tool_call_id"]

                messages.append(message)
        except (json.JSONDecodeError, ValueError) as e:
            _logger.warning(f"Failed to parse conversation messages: {e}")

        return messages

    def add_assistant_message_with_tools(self, content, tool_calls):
        self.ensure_one()

        context = self._load_context()

        assistant_msg = {
            "role": "assistant",
            "content": content or "",
        }

        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        context.append(assistant_msg)

        self.write(
            {
                "context_messages": json.dumps(context),
                "ai_responses": self.ai_responses + 1,
            }
        )

    def add_tool_results(self, tool_results):
        self.ensure_one()

        context = self._load_context()
        existing_tool_ids = {
            msg.get("tool_call_id")
            for msg in context
            if msg.get("role") == "tool" and msg.get("tool_call_id")
        }

        added = 0

        for tool_result in tool_results:
            tool_call_id = tool_result.get("id", "call_" + str(len(context)))
            if tool_call_id in existing_tool_ids:
                continue

            context.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(tool_result.get("result", {})),
                }
            )
            existing_tool_ids.add(tool_call_id)
            added += 1

        self.write(
            {
                "context_messages": json.dumps(context),
                "tool_executions": self.tool_executions + added,
            }
        )

    def action_pause(self):
        self.write({"state": "paused"})
        return True

    def action_resume(self):
        self.write({"state": "active"})
        return True

    def action_complete(self):
        self.write(
            {
                "state": "completed",
                "end_date": fields.Datetime.now(),
            }
        )
        return True

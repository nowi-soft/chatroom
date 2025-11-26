import json
import logging

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

    def add_message(self, message):
        self.ensure_one()

        try:
            context = json.loads(self.context_messages) if self.context_messages else []
        except (json.JSONDecodeError, ValueError) as e:
            _logger.warning(f"Failed to parse conversation context: {e}")
            context = []

        role = "assistant" if message.direction == "outgoing" else "user"

        if message.is_internal:
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

        # Single system message combining temporal instructions + user prompt
        temporal_instructions = """IMPORTANT CONTEXT RULES:
- Each message below includes a timestamp [YYYY-MM-DD HH:MM:SS]
- This is an ongoing conversation - messages are historical context
- Do NOT greet the user again if you already greeted them in previous messages
- Only respond to the most recent message
- Reference previous context when relevant

"""

        system_content = temporal_instructions + self.agent_id.system_prompt

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
            context = json.loads(self.context_messages) if self.context_messages else []
            for msg in context:
                content = msg.get("content", "")

                if msg.get("timestamp") and content and msg.get("role") == "user":
                    from datetime import datetime

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

        try:
            context = json.loads(self.context_messages) if self.context_messages else []
        except (json.JSONDecodeError, ValueError):
            context = []

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

        try:
            context = json.loads(self.context_messages) if self.context_messages else []
        except (json.JSONDecodeError, ValueError):
            context = []

        for tool_result in tool_results:
            context.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_result.get("id", "call_" + str(len(context))),
                    "content": json.dumps(tool_result.get("result", {})),
                }
            )

        self.write(
            {
                "context_messages": json.dumps(context),
                "tool_executions": self.tool_executions + len(tool_results),
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

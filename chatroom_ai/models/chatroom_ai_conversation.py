"""AI Conversation - Tracks context and history for each chat"""

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
            ("pending_approval", "Pending Approval"),
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

    pending_response = fields.Text()

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

        system_content = self.agent_id.system_prompt

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
                message = {
                    "role": msg["role"],
                    "content": msg.get("content", ""),
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

    def action_approve_response(self):
        self.ensure_one()

        if not self.pending_response:
            return False

        self.env["chatroom.message"].create(
            {
                "room_id": self.room_id.id,
                "body": self.pending_response,
                "direction": "outgoing",
                "user_id": self.env.ref("base.user_admin").id,
                "is_ai_generated": True,
            }
        )

        self.write(
            {
                "pending_response": False,
                "state": "active",
            }
        )

        self.agent_id.sudo().write(
            {
                "total_responses": self.agent_id.total_responses + 1,
                "last_response_date": fields.Datetime.now(),
            }
        )

        return True

    def action_reject_response(self):
        self.ensure_one()

        self.write(
            {
                "pending_response": False,
                "state": "paused",
            }
        )

        return True

    def action_complete(self):
        self.write(
            {
                "state": "completed",
                "end_date": fields.Datetime.now(),
            }
        )
        return True

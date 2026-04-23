import json
import logging
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ChatroomRoom(models.Model):
    _inherit = "chatroom.room"

    ai_agent_id = fields.Many2one(
        "chatroom.ai.agent",
        string="AI Agent",
        help="AI Agent assigned to this chat",
    )
    ai_enabled = fields.Boolean(
        string="AI Enabled",
        default=False,
        help="Enable AI auto-responses for this chat",
    )
    ai_conversation_state = fields.Selection(
        [
            ("active", "Active"),
            ("paused", "Paused - Human Intervention"),
            ("completed", "Completed"),
            ("error", "Error"),
            ("testing", "Testing"),
        ],
        string="AI Status",
        default="active",
    )
    ai_context_messages = fields.Text(
        "AI Context (JSON)",
        help="Rolling window of conversation messages in OpenAI format",
    )
    ai_summary = fields.Text(
        "AI Conversation Summary",
        help="Summary of older messages trimmed from the context window",
    )
    ai_error_message = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        rooms = super().create(vals_list)

        for room in rooms:
            if not room.assigned_to_id:
                agent = self.env["chatroom.ai.agent"].search(
                    [("active", "=", True)], limit=1
                )
                if agent:
                    room.write(
                        {
                            "ai_agent_id": agent.id,
                            "ai_enabled": True,
                        }
                    )
                    room._notify_ai_state_change()

        return rooms

    def action_enable_ai(self):
        self.ensure_one()

        if not self.ai_agent_id:
            agent = self.env["chatroom.ai.agent"].search(
                [("active", "=", True)], limit=1
            )
            if agent:
                self.ai_agent_id = agent

        self.write(
            {
                "ai_enabled": True,
                "needs_attention": False,
                "ai_conversation_state": "active",
            }
        )

        self._notify_ai_state_change()
        self._notify_room_updated()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "AI Agent enabled for this chat",
                "type": "success",
            },
        }

    def action_disable_ai(self):
        self.ensure_one()
        self.write(
            {
                "ai_enabled": False,
                "ai_conversation_state": "paused",
            }
        )
        self._notify_ai_state_change()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": "AI Agent disabled for this chat",
                "type": "info",
            },
        }

    def write(self, vals):
        old_needs_attention = {room.id: room.needs_attention for room in self}
        result = super().write(vals)

        if "assigned_to_id" in vals:
            for room in self:
                if vals["assigned_to_id"]:
                    if room.needs_attention:
                        super(ChatroomRoom, room).write({"needs_attention": False})
                    if room.ai_enabled:
                        room.action_disable_ai()
                else:
                    if not room.ai_enabled and room.ai_agent_id:
                        room.action_enable_ai()

        if "needs_attention" in vals:
            for room in self:
                if vals["needs_attention"] and not old_needs_attention.get(room.id):
                    room._notify_urgent_attention()
                elif not vals["needs_attention"] and old_needs_attention.get(room.id):
                    room._notify_room_updated()

        return result

    def _notify_room_updated(self):
        for room in self:
            payload = {
                "id": room.id,
                "name": room.name,
                "assigned_to_id": [room.assigned_to_id.id, room.assigned_to_id.name]
                if room.assigned_to_id
                else False,
                "state": room.state,
                "needs_attention": room.needs_attention,
                "message_count": room.message_count,
                "last_message_date": room.last_message_date.isoformat()
                if room.last_message_date
                else False,
                "last_message_preview": room.last_message_preview,
            }

            chatroom_users = self.env.ref("chatroom.group_chatroom_user").users
            chatroom_managers = self.env.ref("chatroom.group_chatroom_manager").users
            all_chatroom_users = chatroom_users | chatroom_managers

            if room.state in ["assigned", "unassigned"]:
                users_to_notify = all_chatroom_users
            else:
                users_to_notify = chatroom_managers
                if room.assigned_to_id and room.assigned_to_id in chatroom_users:
                    users_to_notify |= room.assigned_to_id

            for user in users_to_notify:
                if user.partner_id:
                    user.partner_id._bus_send("chatroom/room_updated", payload)

    def _notify_ai_state_change(self):
        self.ensure_one()

        chatroom_users = self.env.ref("chatroom.group_chatroom_user").users
        chatroom_managers = self.env.ref("chatroom.group_chatroom_manager").users
        all_chatroom_users = chatroom_users | chatroom_managers

        notified_partners = set()
        for user in all_chatroom_users:
            if user.partner_id and user.partner_id.id not in notified_partners:
                notified_partners.add(user.partner_id.id)
                user.partner_id._bus_send(
                    "chatroom/ai_state_changed",
                    {
                        "room_id": self.id,
                        "ai_enabled": self.ai_enabled,
                    },
                )

    def _notify_urgent_attention(self):
        self.ensure_one()

        try:
            chatroom_user_group = self.env.ref("chatroom.group_chatroom_user")
            chatroom_users = getattr(
                chatroom_user_group, "all_user_ids", chatroom_user_group.users
            )
        except Exception as e:
            _logger.error("Error getting chatroom users: %s", e)
            chatroom_users = self.env["res.users"]

        notified_partners = set()
        for user in chatroom_users:
            if user.partner_id and user.partner_id.id not in notified_partners:
                notified_partners.add(user.partner_id.id)
                self.env["bus.bus"]._sendone(
                    user.partner_id,
                    "chatroom/ai_urgent_attention",
                    {
                        "room_id": self.id,
                        "room_name": self.name,
                        "needs_attention": self.needs_attention,
                    },
                )

    def _load_context(self):
        self.ensure_one()
        try:
            return (
                json.loads(self.ai_context_messages) if self.ai_context_messages else []
            )
        except (json.JSONDecodeError, ValueError) as e:
            _logger.warning("Failed to parse AI conversation context: %s", e)
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

        connector = self.connector_id
        connector_type = (
            (connector.connector_type or "unknown").lower() if connector else "unknown"
        )
        external_id = self.external_id or ""

        lines = ["=== CHANNEL CONTEXT ==="]
        lines.append(f"- Connector type: {connector_type}")
        if external_id:
            lines.append(f"- Channel external_id: {external_id}")

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
        if hasattr(self, "partner_ids") and self.partner_ids:
            partner_names = [p.name for p in self.partner_ids if p.name]
        if partner_names:
            lines.append(f"- Linked contacts in Odoo: {', '.join(partner_names)}")

        lines.append(
            "- Keep questions minimal and action-oriented; "
            "avoid repeating data already available in metadata."
        )

        return "\n".join(lines)

    def add_message(self, message):
        self.ensure_one()

        if message.is_internal:
            return

        context = self._load_context()
        role = "assistant" if message.direction == "outgoing" else "user"

        existing_ids = [msg.get("message_id") for msg in context]
        if message.id in existing_ids:
            _logger.debug(
                "Message ID=%d already in AI context for room ID=%d",
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

        max_length = (
            (self.ai_agent_id.max_conversation_length or 20) if self.ai_agent_id else 20
        )
        if len(context) > max_length:
            old_messages = context[:-max_length]
            context = context[-max_length:]
            self.ai_summary = f"Previous {len(old_messages)} messages summarized."

        self.write({"ai_context_messages": json.dumps(context)})

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
            + (self.ai_agent_id.system_prompt or "")
        )

        if self.ai_agent_id and self.ai_agent_id.knowledge_ids:
            knowledge_content = "\n\n=== KNOWLEDGE BASE ===\n\n"
            for knowledge in self.ai_agent_id.knowledge_ids:
                knowledge_content += knowledge.get_formatted_content()
            system_content += "\n\n" + knowledge_content

        if self.ai_summary:
            system_content += f"\n\n=== CONVERSATION SUMMARY ===\n{self.ai_summary}\n"

        messages.append({"role": "system", "content": system_content})

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

                message = {"role": msg["role"], "content": content}

                if "tool_calls" in msg:
                    message["tool_calls"] = msg["tool_calls"]
                if "tool_call_id" in msg:
                    message["tool_call_id"] = msg["tool_call_id"]

                messages.append(message)
        except (json.JSONDecodeError, ValueError) as e:
            _logger.warning("Failed to parse AI context messages: %s", e)

        return messages

    def add_assistant_message_with_tools(self, content, tool_calls):
        self.ensure_one()

        context = self._load_context()
        assistant_msg = {"role": "assistant", "content": content or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        context.append(assistant_msg)
        self.write({"ai_context_messages": json.dumps(context)})

    def add_tool_results(self, tool_results):
        self.ensure_one()

        context = self._load_context()
        existing_tool_ids = {
            msg.get("tool_call_id")
            for msg in context
            if msg.get("role") == "tool" and msg.get("tool_call_id")
        }

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

        self.write({"ai_context_messages": json.dumps(context)})

    def action_pause_ai_and_request_attention(self):
        self.ensure_one()

        self.write(
            {
                "ai_enabled": False,
                "ai_conversation_state": "paused",
                "state": "unassigned",
                "needs_attention": True,
            }
        )

        agent_name = (
            self.ai_agent_id.name if self.ai_agent_id else self.env._("AI Agent")
        )
        self.env["chatroom.message"].create(
            {
                "room_id": self.id,
                "body": self.env._("⚠️ AI Agent paused: Human intervention required."),
                "direction": "outgoing",
                "is_internal": True,
                "user_id": self.env.ref("base.user_admin").id,
                "author_name": agent_name,
            }
        )

        self._notify_room_updated()

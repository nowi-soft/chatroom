"""AI Agent - Main configuration for automated chat responses"""

import json
import logging

from odoo import api, fields, models

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
        help="Leave 0 to use provider's default",
    )

    system_prompt = fields.Text(
        required=True,
        default="""You are a helpful AI assistant managing customer conversations.
Be professional, friendly, and concise in your responses.
Always maintain context from previous messages in the conversation.""",
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
    knowledge_summary = fields.Text(
        compute="_compute_knowledge_summary",
    )

    tool_ids = fields.Many2many(
        "chatroom.ai.tool",
        "chatroom_ai_agent_tool_rel",
        "agent_id",
        "tool_id",
        "Available Tools",
        help="Actions the agent can perform (create leads, send emails, etc.)",
    )

    response_delay = fields.Integer(
        "Response Delay (seconds)",
        default=2,
        help="Delay before responding (to simulate human typing)",
    )
    max_conversation_length = fields.Integer(
        "Max Conversation Messages",
        default=20,
        help=(
            "Maximum number of messages to include in context "
            "(older messages are summarized)"
        ),
    )

    total_responses = fields.Integer(default=0, readonly=True)
    total_tool_executions = fields.Integer(default=0, readonly=True)
    human_interventions = fields.Integer(default=0, readonly=True)
    last_response_date = fields.Datetime(string="Last Response", readonly=True)

    conversation_ids = fields.One2many(
        "chatroom.ai.conversation",
        "agent_id",
        string="Conversations",
    )
    active_conversation_count = fields.Integer(
        compute="_compute_conversation_counts",
        string="Active Conversations",
    )

    @api.depends("knowledge_ids", "knowledge_ids.content")
    def _compute_knowledge_summary(self):
        for agent in self:
            if agent.knowledge_ids:
                summary = f"{len(agent.knowledge_ids)} documents loaded:\n"
                for knowledge in agent.knowledge_ids[:5]:
                    summary += f"- {knowledge.name}\n"
                if len(agent.knowledge_ids) > 5:
                    summary += f"... and {len(agent.knowledge_ids) - 5} more"
                agent.knowledge_summary = summary
            else:
                agent.knowledge_summary = "No knowledge base configured"

    @api.depends("conversation_ids", "conversation_ids.state")
    def _compute_conversation_counts(self):
        for agent in self:
            agent.active_conversation_count = len(
                agent.conversation_ids.filtered(lambda c: c.state == "active")
            )

    def action_view_conversations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Agent Conversations",
            "res_model": "chatroom.ai.conversation",
            "view_mode": "list,form",
            "domain": [("agent_id", "=", self.id)],
            "context": {"default_agent_id": self.id},
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

    def process_incoming_message(self, message):
        self.ensure_one()

        room = message.room_id

        if not self.should_respond_to_room(room):
            return

        conversation = self.get_or_create_conversation(room)

        conversation.add_message(message)

        try:
            if hasattr(self, "with_delay"):
                self.with_delay(
                    eta=self.response_delay
                ).sudo()._generate_and_send_response(conversation.id)
            else:
                import time

                time.sleep(self.response_delay)
                self._generate_and_send_response(conversation.id)
        except Exception as e:
            _logger.error(f"Error processing message for agent {self.name}: {str(e)}")

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
                _logger.warning(f"No content in AI response for room {room.name}")
                return

            message_vals = {
                "room_id": room.id,
                "body": result["content"],
                "direction": "outgoing",
                "user_id": self.env.ref("base.user_admin").id,
                "is_ai_generated": True,
            }

            self.env["chatroom.message"].sudo().create(message_vals)

            agent.sudo().write(
                {
                    "total_responses": agent.total_responses + 1,
                    "last_response_date": fields.Datetime.now(),
                }
            )

        except Exception as e:
            _logger.error(f"Error generating AI response: {str(e)}")
            conversation.write({"state": "error", "error_message": str(e)})

    def _execute_tool_call(self, conversation, tool_call):
        self.ensure_one()

        if "function" in tool_call:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"].get("arguments", {})
        else:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})

        if isinstance(tool_args, str):
            tool_args = json.loads(tool_args)

        tool = self.tool_ids.filtered(lambda t: t.code_name == tool_name)
        if not tool:
            _logger.warning(f"Tool {tool_name} not found for agent {self.name}")
            return

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

            if isinstance(result, dict) and result.get("error"):
                tool_note = f"🤖 AI Tool Executed: {tool.name} ❌"
            else:
                tool_note = f"🤖 AI Tool Executed: {tool.name} ✅"

            self.env["chatroom.message"].create(
                {
                    "room_id": conversation.room_id.id,
                    "body": tool_note,
                    "direction": "outgoing",
                    "is_internal": True,
                    "user_id": self.env.ref("base.user_admin").id,
                }
            )

            self.sudo().total_tool_calls += 1

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
                    "body": f"🤖 AI Tool Failed: {tool.name} ❌",
                    "direction": "outgoing",
                    "is_internal": True,
                    "user_id": self.env.ref("base.user_admin").id,
                }
            )

            return {"error": str(e)}

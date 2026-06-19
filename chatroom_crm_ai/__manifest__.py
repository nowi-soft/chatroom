{
    "name": "ChatRoom CRM AI",
    "version": "19.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "Let the AI agent create CRM leads from chat conversations",
    "description": """
Gives customer-facing AI agents a tool to capture CRM leads/opportunities
automatically when they detect real commercial intent in a chat.

Components:
- muk_ai.agent extension: crm_lead_enabled flag (Lead when on, Opportunity
  when off) and lead-capture guidance injected into the system prompt.
- create_crm_lead MCP tool: creates a crm.lead linked to the current room
  (reusing chatroom_crm's chatroom_room_ids m2m), filling contact data from
  the room/partner and a conversation summary into the description.
  One open lead per room (updates it instead of duplicating); creates a new
  one if the previous lead is already closed.
""",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom_crm",
        "chatroom_ai_bridge",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}

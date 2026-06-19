Chatroom AI Bridge
==================

Connects ChatRoom (WhatsApp/Telegram inbound) to muk_ai sessions for
automated AI responses, and ships a data-seed "AI Configuration Assistant"
agent that helps non-technical business owners create their own
customer-facing agents via natural conversation.

Components
---------

- ``chatroom.room`` extension: ``muk_ai_agent_id`` (which agent answers this
  room) and ``muk_ai_session_id`` (active session for this room).
- ``chatroom.message`` hook: inbound incoming messages trigger
  ``session.send_message``.
- ``muk_ai.session`` hook: text events on rooms produce outgoing chatroom
  messages.
- ``chatroom_bot`` system user dedicated to customer-facing sessions.
- Data-seed ``muk_ai.agent`` named "AI Configuration Assistant" with a prompt
  that guides business owners through creating their own agents and knowledge
  bases.

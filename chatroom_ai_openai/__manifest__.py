{
    "name": "ChatRoom AI - OpenAI Provider",
    "version": "18.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "OpenAI/ChatGPT integration for AI agents",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom_ai",
    ],
    "external_dependencies": {
        "python": ["openai"],
    },
    "data": [
        "views/chatroom_ai_provider_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}

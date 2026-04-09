{
    "name": "ChatRoom Evolution API",
    "version": "18.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "WhatsApp integration via Evolution API",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom_connector",
    ],
    "data": [
        "views/chatroom_connector_views.xml",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

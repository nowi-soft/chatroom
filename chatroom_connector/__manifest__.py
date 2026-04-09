{
    "name": "ChatRoom Connector",
    "version": "18.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "External messaging platform connectors for ChatRoom",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom",
    ],
    "data": [
        "security/chatroom_connector_security.xml",
        "security/ir.model.access.csv",
        "views/chatroom_connector_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "chatroom_connector/static/src/chatroom_app_patch.js",
            "chatroom_connector/static/src/chatroom_app_patch.xml",
            "chatroom_connector/static/src/chatroom_connector.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

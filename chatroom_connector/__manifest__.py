{
    "name": "ChatRoom Connector",
    "version": "19.0.1.0.0",
    "category": "",
    "summary": "",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom",
    ],
    "data": [
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

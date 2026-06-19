{
    "name": "Chatroom AI Bridge",
    "version": "19.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "Bridge chatroom multi-channel rooms to muk_ai agents",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom",
        "chatroom_connector",
        "muk_ai",
        "muk_ai_knowledge",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/chatroom_user_bot.xml",
        "data/agent_creator.xml",
        "data/ai_dispatch_cron.xml",
        "views/chatroom_room_views.xml",
        "views/chatroom_connector_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/fictional_business.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "chatroom_ai_bridge/static/src/**/*.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

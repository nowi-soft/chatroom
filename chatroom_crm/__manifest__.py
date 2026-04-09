{
    "name": "ChatRoom CRM",
    "version": "18.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "Create CRM leads from chat conversations",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom",
        "crm",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/crm_lead_views.xml",
        "wizard/chatroom_create_lead_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "chatroom_crm/static/src/**/*.js",
            "chatroom_crm/static/src/**/*.xml",
            "chatroom_crm/static/src/**/*.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

{
    "name": "MuK AI Knowledge",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "summary": "Persistent knowledge base for muk_ai agents",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "muk_ai",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_knowledge_views.xml",
        "views/ai_agent_views.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "muk_ai_knowledge/static/src/chat_composer_patch.js",
        ],
    },
    "external_dependencies": {
        "python": ["PyPDF2", "docx", "pandas", "openpyxl"],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

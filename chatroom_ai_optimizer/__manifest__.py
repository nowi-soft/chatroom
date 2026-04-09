{
    "name": "ChatRoom AI Optimizer",
    "version": "18.0.1.0.0",
    "category": "Services/ChatRoom",
    "summary": "Auto-tuning system for AI agent prompts",
    "author": "Nowi",
    "website": "https://nowi.com.ar",
    "license": "LGPL-3",
    "depends": [
        "chatroom_ai",
        "queue_job",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/chatroom_ai_prompt_optimizer_views.xml",
        "views/chatroom_ai_optimization_run_views.xml",
        "views/chatroom_ai_agent_views.xml",
        "views/chatroom_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}

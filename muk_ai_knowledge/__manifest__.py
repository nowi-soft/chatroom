{
    "name": "MuK AI Knowledge",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "summary": "Persistent knowledge base for muk_ai agents",
    "description": """
Adds a persistent knowledge base (muk_ai.knowledge) that can be linked
to muk_ai.agent records via many-to-many. Two injection modes:

- inline: concatenated into the agent's system prompt at session build time.
- tool: exposed via a search_knowledge tool the agent can call on demand.

Supports text/HTML/file content with extraction for PDF, DOCX, XLS/XLSX,
TXT, MD, CSV.
""",
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
    "external_dependencies": {
        "python": ["PyPDF2", "docx", "pandas", "openpyxl"],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}

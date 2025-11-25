"""Knowledge Tags - Categorization for knowledge base documents"""

from odoo import fields, models


class ChatroomAIKnowledgeTag(models.Model):
    _name = "chatroom.ai.knowledge.tag"
    _description = "Knowledge Base Tag"
    _order = "name"

    name = fields.Char(required=True, string="Tag Name", translate=True)
    color = fields.Integer(string="Color Index", default=0)

    _sql_constraints = [
        ("name_uniq", "unique (name)", "Tag name already exists!"),
    ]

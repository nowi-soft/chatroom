from odoo import models

SPREADSHEET_MIMETYPES = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
})


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _ai_check_mimetype(self, mimetype):
        if mimetype in SPREADSHEET_MIMETYPES:
            return
        super()._ai_check_mimetype(mimetype)

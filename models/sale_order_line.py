# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def expand_pack_line(self, write=False):
        """Packs we price ourselves are sold as one line, components never added.

        The pack carries the whole price on its own line (see
        ``product.template._pack_priced_as_plain_product``), so expanding it
        would double the amount and clutter the cart, the delivery and the
        invoice.
        """
        if self.product_id.product_tmpl_id._pack_priced_as_plain_product():
            return
        return super().expand_pack_line(write=write)

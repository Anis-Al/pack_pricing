# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def expand_pack_line(self, write=False):
        """Auto priced packs are sold as one line, components are never added.

        The pack carries the whole price on its own line (see
        ``pack_price_auto``), so expanding it would double the amount and
        clutter the cart, the delivery and the invoice.
        """
        if self.product_id.product_tmpl_id.pack_price_auto:
            return
        return super().expand_pack_line(write=write)

# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class ProductPackLine(models.Model):
    _inherit = "product.pack.line"

    cost_price = fields.Float(
        related="product_id.standard_price",
        string="Cost",
        digits="Product Price",
        help="Unit cost of this component.",
    )
    sale_price = fields.Float(
        related="product_id.lst_price",
        string="Sale Price",
        digits="Product Price",
        help="Unit sales price of this component.",
    )
    subtotal_cost = fields.Float(
        compute="_compute_subtotals",
        string="Cost Subtotal",
        digits="Product Price",
    )
    subtotal_sale = fields.Float(
        compute="_compute_subtotals",
        string="Sale Subtotal",
        digits="Product Price",
    )
    margin = fields.Float(
        compute="_compute_subtotals",
        digits="Product Price",
    )
    margin_percent = fields.Float(
        compute="_compute_subtotals",
        string="Margin (%)",
    )

    @api.depends("quantity", "cost_price", "sale_price", "sale_discount")
    def _compute_subtotals(self):
        for line in self:
            line.subtotal_cost = line.quantity * line.cost_price
            line.subtotal_sale = (
                line.quantity * line.sale_price * (1 - line.sale_discount / 100.0)
            )
            line.margin = line.subtotal_sale - line.subtotal_cost
            line.margin_percent = (
                line.margin / line.subtotal_sale * 100.0 if line.subtotal_sale else 0.0
            )

    def _sync_parent_packs(self):
        self.mapped("parent_product_id.product_tmpl_id")._sync_pack_prices()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_parent_packs()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self._sync_parent_packs()
        return res

    def unlink(self):
        templates = self.mapped("parent_product_id.product_tmpl_id")
        res = super().unlink()
        templates._sync_pack_prices()
        return res

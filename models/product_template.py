# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pack_price_auto = fields.Boolean(
        "Auto Pack Pricing",
        help="Compute this pack's cost and sales price from its components, "
        "publish its discount in the Packs pricelist, and sell it as a single "
        "order line (components are never added to the order).",
    )
    pack_total_cost = fields.Float(
        compute="_compute_pack_totals",
        string="Components Cost",
        digits="Product Price",
    )
    pack_total_sale = fields.Float(
        compute="_compute_pack_totals",
        string="Components Sales Price",
        digits="Product Price",
    )
    pack_margin = fields.Float(
        compute="_compute_pack_totals",
        string="Pack Margin",
        digits="Product Price",
    )
    pack_margin_percent = fields.Float(
        compute="_compute_pack_totals",
        string="Pack Margin (%)",
    )
    pack_margin_after_discount = fields.Float(
        compute="_compute_pack_totals",
        string="Margin After Discount",
        digits="Product Price",
        help="Margin left once the pack discount is applied.",
    )
    pack_discount = fields.Float(
        "Pack Discount (%)",
        digits="Discount",
        help="Discount published as a pricelist item in the Packs pricelist.",
    )
    pack_price_final = fields.Float(
        compute="_compute_pack_totals",
        string="Price After Discount",
        digits="Product Price",
    )

    @api.depends(
        "pack_line_ids.subtotal_cost",
        "pack_line_ids.subtotal_sale",
        "pack_discount",
    )
    def _compute_pack_totals(self):
        for tmpl in self:
            tmpl.pack_total_cost = sum(tmpl.pack_line_ids.mapped("subtotal_cost"))
            tmpl.pack_total_sale = sum(tmpl.pack_line_ids.mapped("subtotal_sale"))
            tmpl.pack_margin = tmpl.pack_total_sale - tmpl.pack_total_cost
            tmpl.pack_margin_percent = (
                tmpl.pack_margin / tmpl.pack_total_sale * 100.0
                if tmpl.pack_total_sale
                else 0.0
            )
            tmpl.pack_price_final = tmpl.pack_total_sale * (
                1 - tmpl.pack_discount / 100.0
            )
            tmpl.pack_margin_after_discount = (
                tmpl.pack_price_final - tmpl.pack_total_cost
            )

    @api.constrains("pack_price_auto", "pack_ok")
    def _check_pack_price_auto(self):
        for tmpl in self.filtered("pack_price_auto"):
            if not tmpl.pack_ok:
                raise ValidationError(
                    self.env._("Auto Pack Pricing only applies to pack products.")
                )

    def _is_pack_to_be_handled(self):
        """Auto priced packs are priced like a plain product.

        ``product_pack`` otherwise forces the pack's own price to 0 and rebuilds
        it from the components on every price request, which discards both the
        price we roll up into ``list_price`` and any pricelist item set on the
        pack (see ``product_pack/models/product_pricelist.py``). Since the pack
        already carries the whole amount, and its components are never expanded
        into the order, that second roll-up has to stay out of the way whatever
        the Pack Display Type is.
        """
        self.ensure_one()
        if self.pack_price_auto:
            return False
        return super()._is_pack_to_be_handled()

    @api.constrains("pack_discount")
    def _check_pack_discount(self):
        for tmpl in self:
            if not 0.0 <= tmpl.pack_discount < 100.0:
                raise ValidationError(
                    self.env._(
                        "The pack discount must be between 0% (included) and "
                        "100% (excluded)."
                    )
                )

    def _sync_pack_prices(self):
        """Push the component roll-up onto the pack product and its pricelist item."""
        if self.env.context.get("pack_price_sync"):
            return
        # A pack without components has nothing to roll up: leave the manually
        # entered prices alone instead of zeroing them.
        packs = self.filtered(
            lambda t: t.pack_ok and t.pack_price_auto and t.pack_line_ids
        )
        for tmpl in packs.with_context(pack_price_sync=True):
            vals = {}
            if tmpl.currency_id.compare_amounts(tmpl.list_price, tmpl.pack_total_sale):
                vals["list_price"] = tmpl.pack_total_sale
            if tmpl.cost_currency_id.compare_amounts(
                tmpl.standard_price, tmpl.pack_total_cost
            ):
                vals["standard_price"] = tmpl.pack_total_cost
            if vals:
                tmpl.write(vals)
            tmpl._sync_pack_pricelist_item()
        # ponytail: a pack used inside another auto pack is not cascaded, one
        # level is enough here. Reopen and save the outer pack to refresh it.

    def _pack_effective_discount(self):
        """Discount actually published, 0 for anything that is not an auto pack."""
        self.ensure_one()
        return self.pack_discount if self.pack_ok and self.pack_price_auto else 0.0

    def _sync_pack_pricelist_item(self):
        pricelist = self.env.ref(
            "pack_pricing.pricelist_packs", raise_if_not_found=False
        )
        if not pricelist:
            return
        item_model = self.env["product.pricelist.item"].sudo()
        for tmpl in self:
            item = item_model.search(
                [
                    ("pricelist_id", "=", pricelist.id),
                    ("applied_on", "=", "1_product"),
                    ("product_tmpl_id", "=", tmpl.id),
                ],
                limit=1,
            )
            discount = tmpl._pack_effective_discount()
            if not discount:
                item.unlink()
                continue
            vals = {
                "pricelist_id": pricelist.id,
                "applied_on": "1_product",
                "product_tmpl_id": tmpl.id,
                "compute_price": "percentage",
                "percent_price": discount,
                "base": "list_price",
                "min_quantity": 0,
            }
            if item:
                item.write(vals)
            else:
                item_model.create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._sync_pack_prices()
        return templates

    def write(self, vals):
        if vals.get("pack_ok") is False:
            # Unticking "Is a Pack" leaves nothing to roll up: drop auto pricing
            # with it instead of failing the constraint and rolling the save back.
            vals = dict(vals, pack_price_auto=False)
        res = super().write(vals)
        if self.env.context.get("pack_price_sync"):
            return res
        if {"pack_ok", "pack_price_auto"} & vals.keys():
            # Auto pricing (or the pack flag itself) was just switched off:
            # drop the pricelist item that nothing displays anymore.
            self._sync_pack_pricelist_item()
        self._sync_pack_prices()
        if {"list_price", "standard_price"} & vals.keys():
            # A component price changed: refresh the packs using it.
            self.mapped(
                "product_variant_ids.used_in_pack_line_ids.parent_product_id"
                ".product_tmpl_id"
            )._sync_pack_prices()
        return res

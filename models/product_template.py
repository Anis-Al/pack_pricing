# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Packs are always sold as one line here, so the display type is noise:
    # default it and hide it in the view.
    pack_type = fields.Selection(default="non_detailed")
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
    pack_margin_percent_after_discount = fields.Float(
        compute="_compute_pack_totals",
        string="Margin After Discount (%)",
    )
    discount = fields.Boolean(
        "Apply Pack Discount",
        help="Publish a discount for this pack in the Packs pricelist. "
        "Unticking it clears the discount and removes the pricelist item.",
    )
    pack_discount = fields.Float(
        "Pack Discount (%)",
        digits="Discount",
        help="Discount published as a pricelist item in the Packs pricelist.",
    )
    pack_price_before_discount = fields.Float(
        compute="_compute_pack_totals",
        string="Price Before Discount",
        digits="Product Price",
        help="What the pack discount is taken off: the component roll-up when "
        "auto pricing is on, the product's own sales price when it is off.",
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
        "discount",
        "pack_price_auto",
        "list_price",
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
            # Without auto pricing nothing rolls the components up into
            # list_price, so the roll-up is not what gets discounted: the
            # product's own sales price is.
            tmpl.pack_price_before_discount = (
                tmpl.pack_total_sale if tmpl.pack_price_auto else tmpl.list_price
            )
            # A stored pack_discount with the switch off is dead data (import,
            # or a discount someone turned off): the tab must not show it.
            discount = tmpl.pack_discount if tmpl.discount else 0.0
            tmpl.pack_price_final = tmpl.pack_price_before_discount * (
                1 - discount / 100.0
            )
            tmpl.pack_margin_after_discount = (
                tmpl.pack_price_final - tmpl.pack_total_cost
            )
            tmpl.pack_margin_percent_after_discount = (
                tmpl.pack_margin_after_discount / tmpl.pack_price_final * 100.0
                if tmpl.pack_price_final
                else 0.0
            )

    @api.onchange("pack_ok")
    def _onchange_pack_ok(self):
        self.pack_price_auto = self.pack_ok

    @api.onchange("discount")
    def _onchange_discount(self):
        if not self.discount:
            self.pack_discount = 0.0

    @api.constrains("pack_price_auto", "pack_ok")
    def _check_pack_price_auto(self):
        for tmpl in self.filtered("pack_price_auto"):
            if not tmpl.pack_ok:
                raise ValidationError(
                    self.env._("Auto Pack Pricing only applies to pack products.")
                )

    def _pack_priced_as_plain_product(self):
        """A pack's own ``list_price`` is its price. Components add nothing.

        True for **every** pack, not just an auto priced one. ``pack_type`` is
        defaulted to ``non_detailed`` and hidden by this module, and that is the
        value on which OCA zeroes the pack's own price and re-sums the
        components — on the pricelist path
        (``product_pack/models/product_pricelist.py:14``) *and* on ``lst_price``
        (``product_pack/models/product_product.py:37``). With the field hidden
        there is no longer a setting a user could pick to escape that, so a
        hand-typed sales price would be silently ignored everywhere.

        The two switches are therefore purely additive on top of this:
        ``pack_price_auto`` fills ``list_price`` in from the components,
        ``discount`` publishes a percentage off it. Neither decides *whether*
        the pack's own price counts.

        Single source of truth: ``_is_pack_to_be_handled`` and
        ``sale.order.line.expand_pack_line`` must agree, or the order gets the
        pack's full price *and* a line per component.
        """
        self.ensure_one()
        return self.pack_ok

    def _is_pack_to_be_handled(self):
        """Packs we price ourselves are priced like a plain product.

        ``product_pack`` otherwise forces the pack's own price to 0 and rebuilds
        it from the components on every price request, which discards both the
        price in ``list_price`` and any pricelist item set on the pack (see
        ``product_pack/models/product_pricelist.py:14``). Since the pack already
        carries the whole amount, and its components are never expanded into the
        order, that second roll-up has to stay out of the way whatever the Pack
        Display Type is.
        """
        self.ensure_one()
        if self._pack_priced_as_plain_product():
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
        """Push the component roll-up onto the pack product.

        The pricelist item is *not* synced here: it hangs off ``discount``,
        which no longer follows ``pack_price_auto``. See ``write`` / ``create``.
        """
        if self.env.context.get("pack_price_sync"):
            return

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
        # ponytail: a pack used inside another auto pack is not cascaded, one
        # level is enough here. Reopen and save the outer pack to refresh it.

    def _pack_effective_discount(self):
        """Discount actually published, 0 unless the pack asked for one.

        Deliberately independent of ``pack_price_auto``: the switch is
        ``discount``, so a pack can carry a pricelist discount without having
        its prices rolled up from its components.
        """
        self.ensure_one()
        return self.pack_discount if self.pack_ok and self.discount else 0.0

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
        # Only packs can ever own an item, and product creation is hot enough
        # that one search per plain product is worth skipping.
        templates.filtered("pack_ok")._sync_pack_pricelist_item()
        return templates

    def write(self, vals):
        if vals.get("pack_ok") is False:
            # Unticking "Is a Pack" leaves nothing to roll up: drop auto pricing
            # with it instead of failing the constraint and rolling the save back.
            vals = dict(vals, pack_price_auto=False)
        if vals.get("discount") is False:
            # The switch is off: clear the percentage it controls so nothing
            # stale is left behind to reappear when it is turned back on.
            vals = dict(vals, pack_discount=0.0)
        res = super().write(vals)
        if self.env.context.get("pack_price_sync"):
            return res
        if {"pack_ok", "discount", "pack_discount"} & vals.keys():
            # Anything the published percentage is derived from just moved.
            self._sync_pack_pricelist_item()
        self._sync_pack_prices()
        if {"list_price", "standard_price"} & vals.keys():
            # A component price changed: refresh the packs using it.
            self.mapped(
                "product_variant_ids.used_in_pack_line_ids.parent_product_id"
                ".product_tmpl_id"
            )._sync_pack_prices()
        return res

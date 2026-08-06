# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestPackPricing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product_model = cls.env["product.product"]
        cls.component_b = product_model.create(
            {"name": "Component B", "list_price": 200.0, "standard_price": 100.0}
        )
        cls.component_c = product_model.create(
            {"name": "Component C", "list_price": 100.0, "standard_price": 50.0}
        )
        cls.pack = product_model.create(
            {
                "name": "Pack A",
                "list_price": 0.0,
                "pack_ok": True,
                "pack_type": "detailed",
                "pack_component_price": "ignored",
                "pack_price_auto": True,
                "discount": True,
            }
        )
        cls.env["product.pack.line"].create(
            [
                {
                    "parent_product_id": cls.pack.id,
                    "product_id": cls.component_b.id,
                    "quantity": 2.0,
                },
                {
                    "parent_product_id": cls.pack.id,
                    "product_id": cls.component_c.id,
                    "quantity": 3.0,
                },
            ]
        )
        cls.template = cls.pack.product_tmpl_id
        cls.packs_pricelist = cls.env.ref("pack_pricing.pricelist_packs")

    def test_prices_rolled_up_from_components(self):
        # 2 * 200 + 3 * 100 = 700 ; 2 * 100 + 3 * 50 = 350
        self.assertEqual(self.template.pack_total_sale, 700.0)
        self.assertEqual(self.template.pack_total_cost, 350.0)
        self.assertEqual(self.template.pack_margin, 350.0)
        self.assertEqual(self.template.pack_margin_percent, 50.0)
        self.assertEqual(self.template.list_price, 700.0)
        self.assertEqual(self.template.standard_price, 350.0)

    def test_component_price_change_refreshes_pack(self):
        self.component_b.product_tmpl_id.list_price = 300.0
        self.assertEqual(self.template.list_price, 900.0)

    def test_discount_creates_pricelist_item(self):
        self.template.pack_discount = 10.0
        self.assertEqual(self.template.pack_price_final, 630.0)
        self.assertEqual(self.template.pack_margin_after_discount, 280.0)
        self.assertAlmostEqual(
            self.template.pack_margin_percent_after_discount, 44.44, places=2
        )
        item = self.env["product.pricelist.item"].search(
            [
                ("pricelist_id", "=", self.packs_pricelist.id),
                ("product_tmpl_id", "=", self.template.id),
            ]
        )
        self.assertEqual(len(item), 1)
        self.assertEqual(item.compute_price, "percentage")
        self.assertEqual(item.percent_price, 10.0)
        self.assertEqual(
            self.packs_pricelist._get_product_price(self.pack, 1.0), 630.0
        )
        # Clearing the discount removes the item again.
        self.template.pack_discount = 0.0
        self.assertFalse(item.exists())

    def test_pack_sold_as_single_line(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "order_line": [(0, 0, {"product_id": self.pack.id, "product_uom_qty": 1})],
            }
        )
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.price_unit, 700.0)

    def test_empty_pack_keeps_manual_prices(self):
        empty_pack = self.env["product.product"].create(
            {
                "name": "Pack Without Components",
                "list_price": 500.0,
                "pack_ok": True,
                "pack_type": "detailed",
                "pack_component_price": "ignored",
                "pack_price_auto": True,
            }
        )
        self.assertEqual(empty_pack.list_price, 500.0)

    def test_disabling_discount_removes_item(self):
        self.template.pack_discount = 10.0
        item = self.env["product.pricelist.item"].search(
            [
                ("pricelist_id", "=", self.packs_pricelist.id),
                ("product_tmpl_id", "=", self.template.id),
            ]
        )
        self.assertTrue(item)
        self.template.discount = False
        self.assertEqual(self.template.pack_discount, 0.0)
        self.assertEqual(self.template.pack_price_final, 700.0)
        self.assertFalse(item.exists())

    def test_auto_pricing_does_not_drive_the_discount(self):
        """``discount`` is the only switch for the pricelist item."""
        self.template.pack_discount = 10.0
        item = self.env["product.pricelist.item"].search(
            [
                ("pricelist_id", "=", self.packs_pricelist.id),
                ("product_tmpl_id", "=", self.template.id),
            ]
        )
        self.assertTrue(item)
        self.template.pack_price_auto = False
        self.assertTrue(item.exists())
        self.assertEqual(item.percent_price, 10.0)

    def test_discount_base_without_auto_pricing_is_list_price(self):
        self.template.pack_discount = 10.0
        self.assertEqual(self.template.pack_price_before_discount, 700.0)
        self.template.pack_price_auto = False
        self.template.list_price = 800.0
        self.assertEqual(self.template.pack_price_before_discount, 800.0)
        self.assertEqual(self.template.pack_price_final, 720.0)
        # The roll-up is untouched: only the discount base moved.
        self.assertEqual(self.template.pack_total_sale, 700.0)

    def test_discount_applies_without_auto_pricing(self):
        """What the tab shows is what the customer pays, auto pricing or not."""
        self.template.pack_price_auto = False
        self.template.pack_discount = 10.0
        self.template.list_price = 800.0
        self.assertFalse(self.template._is_pack_to_be_handled())
        self.assertEqual(
            self.packs_pricelist._get_product_price(self.pack, 1.0), 720.0
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "pricelist_id": self.packs_pricelist.id,
                "order_line": [(0, 0, {"product_id": self.pack.id, "product_uom_qty": 1})],
            }
        )
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.price_unit, 720.0)

    def test_hand_typed_price_wins_with_both_switches_off(self):
        """`pack_type` is hidden, so nothing may re-sum the components."""
        self.template.pack_price_auto = False
        self.template.discount = False
        self.template.list_price = 2000.0
        self.assertFalse(self.template._is_pack_to_be_handled())
        # The shop's public price and the pricelist price both honour it.
        self.assertEqual(self.pack.lst_price, 2000.0)
        self.assertEqual(
            self.packs_pricelist._get_product_price(self.pack, 1.0), 2000.0
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "order_line": [(0, 0, {"product_id": self.pack.id, "product_uom_qty": 1})],
            }
        )
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.price_unit, 2000.0)

    def test_discount_off_ignores_a_stale_percentage(self):
        self.template.pack_discount = 10.0
        self.template.discount = False
        # Data written straight onto the field, bypassing the form.
        self.template.with_context(pack_price_sync=True).pack_discount = 10.0
        self.assertEqual(self.template.pack_price_final, 700.0)
        self.assertEqual(self.template._pack_effective_discount(), 0.0)

    def test_disabling_pack_ok_removes_item(self):
        self.template.pack_discount = 10.0
        item = self.env["product.pricelist.item"].search(
            [
                ("pricelist_id", "=", self.packs_pricelist.id),
                ("product_tmpl_id", "=", self.template.id),
            ]
        )
        self.assertTrue(item)
        self.template.pack_ok = False
        self.assertFalse(self.template.pack_price_auto)
        self.assertFalse(item.exists())

    def test_discount_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            self.template.pack_discount = 120.0
        with self.assertRaises(ValidationError):
            self.template.pack_discount = -5.0

    def test_non_detailed_pack_keeps_its_own_price(self):
        """product_pack must not rebuild the price of an auto pack, any mode."""
        self.template.pack_type = "non_detailed"
        self.template.pack_discount = 10.0
        self.assertFalse(self.template._is_pack_to_be_handled())
        self.assertEqual(self.template.list_price, 700.0)
        self.assertEqual(
            self.packs_pricelist._get_product_price(self.pack, 1.0), 630.0
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "pricelist_id": self.packs_pricelist.id,
                "order_line": [(0, 0, {"product_id": self.pack.id, "product_uom_qty": 1})],
            }
        )
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.price_unit, 630.0)

    def test_auto_pricing_requires_a_pack(self):
        plain = self.env["product.product"].create({"name": "Plain"})
        with self.assertRaises(ValidationError):
            plain.pack_price_auto = True

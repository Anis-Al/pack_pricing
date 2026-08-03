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

    def test_disabling_auto_pricing_removes_item(self):
        self.template.pack_discount = 10.0
        item = self.env["product.pricelist.item"].search(
            [
                ("pricelist_id", "=", self.packs_pricelist.id),
                ("product_tmpl_id", "=", self.template.id),
            ]
        )
        self.assertTrue(item)
        self.template.pack_price_auto = False
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

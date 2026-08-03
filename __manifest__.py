# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Pack Pricing",
    "version": "19.0.1.0.0",
    "category": "Sales",
    "summary": "Cost/sale/margin roll-up on pack products, pack discount as a "
    "Packs pricelist item, single-line packs on the website",
    "author": "Custom",
    "license": "AGPL-3",
    "depends": ["sale_product_pack", "website_sale"],
    "data": [
        "data/product_pricelist_data.xml",
        "views/product_pack_line_views.xml",
        "views/product_template_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}

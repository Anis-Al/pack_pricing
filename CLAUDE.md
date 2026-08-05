# pack_pricing

Odoo 19 addon. Extends `product_pack` + `sale_product_pack` (OCA) and `website_sale`.

Three things, all gated behind one opt-in flag `pack_price_auto` on `product.template`:

1. Pack tab shows each component's cost, sale price, subtotals and margin, rolled up to
   pack totals, and writes those totals onto the pack's `list_price` / `standard_price`.
2. `pack_discount` is published as a pricelist item in the **Packs** pricelist.
3. The pack is sold as a single order line — components are never expanded into the order.

Flag off = OCA behaviour, untouched.

## The rule everything depends on

`product_pack` hijacks pricing when `_is_pack_to_be_handled()` is True
(`../product_pack/models/product_template.py:111`), i.e. `pack_type == 'non_detailed'` or
`pack_component_price == 'totalized'`. In that path the pack's **own** price is forced to 0
and rebuilt from components, so **a pricelist item on the pack product is silently ignored**.

`pack_pricing` overrides `_is_pack_to_be_handled()` to return **False** whenever
`pack_price_auto` is set. An auto pack is priced like a plain product: the roll-up lives in
its `list_price`, and pricelist items apply normally. Without that override the discount
disappears with no error.

That is also why auto packs work in **any** Pack Display Type. For them `pack_type` and
`pack_component_price` are cosmetic — components are never expanded into an order either
way, so nothing double-counts.

If a pack discount "doesn't apply", check `pack_price_auto` first: with the flag off,
`pack_discount` is stored but never published.

## Files

| File | Owns |
|---|---|
| `models/product_pack_line.py` | per-component `cost_price`, `sale_price`, `subtotal_*`, `margin`, `margin_percent`; resyncs the parent pack on create/write/unlink |
| `models/product_template.py` | `pack_price_auto`, pack totals, `pack_discount`, both constraints, `_sync_pack_prices`, `_sync_pack_pricelist_item` |
| `models/sale_order_line.py` | suppresses `expand_pack_line` for auto packs |
| `data/product_pricelist_data.xml` | the Packs pricelist, `noupdate`, bound to `website.default_website` |
| `views/product_pack_line_views.xml` | price/margin columns, inherits the `sale_product_pack` views (not `product_pack`'s — `sale_discount` must already be there) |
| `views/product_template_views.xml` | margin + discount groups in the Pack tab; `list_price`/`standard_price` readonly when auto |

## Pack tab layout

The component list already sums `subtotal_cost`, `subtotal_sale` and `margin`, so the two
groups under it must not repeat those numbers. Left group ("Margin") shows `pack_margin`
and `pack_margin_after_discount` (both money), right group shows `pack_discount` and
`pack_price_final`. `pack_total_cost`, `pack_total_sale` and `pack_margin_percent` still
compute — the sync and the tests read them — but no view renders them.

Both groups stay visible; only `pack_margin_after_discount` hides at `pack_discount = 0`
(hiding the whole Margin group made the tab jump on every discount edit). The discount
group carries `class="alert alert-info"` — backend bootstrap, no module scss.

`pack_margin_after_discount` = `pack_price_final - pack_total_cost`. The discount comes off
revenue, never off cost, so it burns margin faster than its own percentage: 10% off 700
costs 70 of 350 margin.

## Sync

`_sync_pack_prices()` is the single write path. Called from:

- `product.template.create` / `write`
- `product.pack.line.create` / `write` / `unlink` → `_sync_parent_packs()`
- a `list_price`/`standard_price` write on any component → refreshes packs using it, via
  `product_variant_ids.used_in_pack_line_ids.parent_product_id.product_tmpl_id`

Re-entry is blocked by the **`pack_price_sync` context key**. Set it if you need to write a
pack's prices without triggering the chain. Both `_sync_pack_prices` and
`product.template.write` bail out early when it is present.

Pricelist item state is derived from `_pack_effective_discount()`, which returns 0 unless
`pack_ok and pack_price_auto` — that is what deletes the item when either flag is switched
off. `write` calls `_sync_pack_pricelist_item()` directly when those keys are in vals,
because `_sync_pack_prices` filters them out by then.

Writing `pack_ok = False` also forces `pack_price_auto = False` in the same vals. Without
that the `_check_pack_price_auto` constraint aborts the save and the pricelist item stays.

## Invariants — break these and something silently rots

- A pack with **no** components is skipped by the sync. Otherwise ticking the flag on an
  existing product zeroes its price.
- Non-auto packs must end up with **no** item in the Packs pricelist.
- `standard_price` is company-dependent, and writing it on a stockable product with
  AVCO/FIFO and on-hand stock creates stock revaluation entries. Keep auto packs `consu`.
- `pack_discount` is `0 <= d < 100`. Negative would be a pricelist markup, `>= 100` a
  negative sale price.

## Deliberate limits — don't "fix" without asking

- The Packs pricelist reliably applies to **public shoppers only**; a logged-in partner's
  own `property_product_pricelist` wins (`../../addons/website_sale/models/website.py:588`).
- Nested auto packs (a pack inside a pack) do not cascade — one level, marked with a
  `ponytail:` comment in `_sync_pack_prices`.
- Pricelist items are written with `sudo()`: product write access implies pricelist item
  creation. Accepted so salespeople don't hit AccessError on save. Open question.
- `../custom_pack_website`'s confirm-time section surgery is dead code for auto packs (no
  child lines exist to move). Left alone for non-auto packs.

## Conventions

AGPL-3, matching the OCA modules below it.

Odoo 19 syntax: `<list>`, direct-expression `invisible="not pack_ok"`, `sum="Label"` on list
fields is still valid. `self.env._("...")` with **no `%%` escaping** unless format args are
actually passed — with no args the formatting step is skipped and `%%` renders literally
(`../../odoo/tools/translate.py:428`).

## Tests

```bash
odoo -d YOURDB -i pack_pricing --test-enable --test-tags /pack_pricing --stop-after-init
```

`tests/test_pack_pricing.py` is the reference scenario: component B costs 100 / sells 200,
component C costs 50 / sells 100, pack = 2×B + 3×C → cost 350, sale 700, margin 350 (50%),
discount 10% → 630 on the Packs pricelist, margin after discount 280, one order line.

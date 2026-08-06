# pack_pricing

Odoo 19 addon. Extends `product_pack` + `sale_product_pack` (OCA) and `website_sale`.

Every pack is priced from its own `list_price` and sold as one order line — see
"The rule everything depends on". On top of that, two independent switches on
`product.template`.

`pack_price_auto` gates:

1. Pack tab shows each component's cost, sale price, subtotals and margin, rolled up to
   pack totals, and writes those totals onto the pack's `list_price` / `standard_price`.

`discount` gates:

2. `pack_discount` is published as a pricelist item in the **Packs** pricelist.

Both off = a pack priced by hand, at whatever `list_price` someone typed.

The flag tracks `pack_ok` in the form (`_onchange_pack_ok`): ticking "Is a Pack" turns auto
pricing on, unticking turns it off. No stored `default=True` — that would sit on every
non-pack product and trip `_check_pack_price_auto`. Packs created by import or data files
get no onchange, so they stay off.

## The rule everything depends on

`product_pack` hijacks pricing when `_is_pack_to_be_handled()` is True
(`../product_pack/models/product_template.py:111`), i.e. `pack_type == 'non_detailed'` or
`pack_component_price == 'totalized'`. In that path the pack's **own** price is forced to 0
and rebuilt from components, so **a pricelist item on the pack product is silently ignored**.

`pack_pricing` overrides `_is_pack_to_be_handled()` to return **False** whenever
`_pack_priced_as_plain_product()` is True — which is **every pack**, since that method is
just `self.pack_ok`. A pack is priced like a plain product: the whole amount lives in its
`list_price`, and pricelist items apply normally.

It has to be every pack, not only auto priced ones, because this module defaults `pack_type`
to `non_detailed` and **hides the field**. `non_detailed` is exactly the value OCA zeroes the
pack's own price on, and there is no longer a setting a user could pick to escape it. Leave
any pack out of the override and its hand-typed sales price is silently ignored — on the
pricelist path *and* on `lst_price`
(`../product_pack/models/product_product.py:37`), i.e. the shop's public price too.

So the two switches are purely additive on top of this: `pack_price_auto` fills `list_price`
in from the components, `discount` publishes a percentage off it. Neither decides *whether*
the pack's own price counts.

`_pack_priced_as_plain_product()` is the single source of truth, and
`sale.order.line.expand_pack_line` uses the *same* method. They must agree — one saying
"the pack carries the whole price" while the other expands the components gives an order
with both. Today both are unconditional for packs; keep them reading the same method if
either ever grows a condition again.

**Consequence: OCA's component-sum pricing and line expansion no longer run for any pack in
this database.** That was accepted deliberately (2026-08-06) — the alternative was a
hand-typed price that vanishes with no warning.

That is also why auto packs work in **any** Pack Display Type. For them `pack_type` and
`pack_component_price` are cosmetic — components are never expanded into an order either
way, so nothing double-counts.

Because it is cosmetic, `pack_type` is defaulted to `non_detailed` here (attribute-only
override in `models/product_template.py`) and hidden in the Pack tab (`invisible="1"`,
`required="0"` — the default fills it, so OCA's `required="pack_ok"` has nothing to guard).
`pack_component_price` and `pack_modifiable` then hide themselves through OCA's own
`invisible="pack_type != 'detailed'"`. Existing records keep whatever they had; the default
only fires on create.

What any pack is charged is therefore its own `list_price` minus the item, if it has one.
That is what `pack_price_before_discount` displays, so the tab and the customer agree.

If a pack discount "doesn't apply", check `discount`: with it off, `pack_discount` is
stored but never published.

## Files

| File | Owns |
|---|---|
| `models/product_pack_line.py` | per-component `cost_price`, `sale_price`, `subtotal_*`, `margin`, `margin_percent`; resyncs the parent pack on create/write/unlink |
| `models/product_template.py` | `pack_price_auto`, `discount`, pack totals, `pack_discount`, both constraints, `_sync_pack_prices`, `_sync_pack_pricelist_item` |
| `models/sale_order_line.py` | suppresses `expand_pack_line` via `_pack_priced_as_plain_product` |
| `data/product_pricelist_data.xml` | the Packs pricelist, `noupdate`, bound to `website.default_website` |
| `views/product_pack_line_views.xml` | price/margin columns, inherits the `sale_product_pack` views (not `product_pack`'s — `sale_discount` must already be there) |
| `views/product_template_views.xml` | margin + discount groups in the Pack tab; `list_price`/`standard_price` readonly when auto |

## Pack tab layout

The component list already sums `subtotal_cost`, `subtotal_sale` and `margin`, so the two
groups under it must not repeat those numbers. Left group ("Margin") shows `pack_margin`
and `pack_margin_after_discount` (both money), each followed inline by its percentage
(`pack_margin_percent`, `pack_margin_percent_after_discount`) in a `text-muted`
`font-size: 0.7em` span (bootstrap `.small` at 0.875em was not small enough) —
`<label>` + `<div class="o_row">` per row, since a plain `<field>` can't carry a suffix.
Right group shows `pack_price_before_discount`, `pack_discount` and `pack_price_final`.
`pack_total_cost` and `pack_total_sale` still compute — the sync and the tests read them —
but no view renders them.

`pack_price_before_discount` is the base the discount comes off, and it **switches on
`pack_price_auto`**: the component roll-up (`pack_total_sale`) when auto pricing is on, the
product's own `list_price` when it is off. Without auto pricing nothing copies the roll-up
into `list_price`, so the roll-up is not what a pricelist item would discount. With auto
pricing on the two are equal anyway once `_sync_pack_prices` has run — the branch only
matters for a non-auto pack, or an auto pack with no components (sync skips those, so
`pack_total_sale` is 0 while `list_price` is whatever was typed).

`pack_margin` stays the component margin (`pack_total_sale - pack_total_cost`) and does not
follow that switch, so on a non-auto pack with a hand-typed `list_price` the Margin group
reads before-discount off the roll-up and after-discount off `list_price`. Harmless today —
the Margin group is only meaningful for auto packs, where the two agree.

Both percentages are margin over **revenue**, not over cost: `pack_margin / pack_total_sale`
and `pack_margin_after_discount / pack_price_final`. Reference scenario: 50% before a 10%
discount, 44.44% after.

The wrapper `<group>` holding both carries `invisible="not discount"` — one modifier hides
Margin and Pack Discount together. Inside, both groups stay visible; only
`pack_margin_after_discount` hides at `pack_discount = 0` (hiding the Margin group *on the
percentage* made the tab jump on every discount edit). The discount group carries
`class="alert alert-info"` — backend bootstrap, no module scss.

`pack_margin_after_discount` = `pack_price_final - pack_total_cost`. The discount comes off
revenue, never off cost, so it burns margin faster than its own percentage: 10% off 700
costs 70 of 350 margin.

`_compute_pack_totals` depends on `list_price`, which `_sync_pack_prices` also writes. No
cycle — the compute only reads it — but it does mean the whole block recomputes on every
price sync.

## Sync

`_sync_pack_prices()` is the single write path. Called from:

- `product.template.create` / `write`
- `product.pack.line.create` / `write` / `unlink` → `_sync_parent_packs()`
- a `list_price`/`standard_price` write on any component → refreshes packs using it, via
  `product_variant_ids.used_in_pack_line_ids.parent_product_id.product_tmpl_id`

Re-entry is blocked by the **`pack_price_sync` context key**. Set it if you need to write a
pack's prices without triggering the chain. Both `_sync_pack_prices` and
`product.template.write` bail out early when it is present.

The pricelist item is on a **separate path** — `_sync_pack_prices` does not touch it,
because it filters down to auto packs and `discount` no longer follows `pack_price_auto`.
`_sync_pack_pricelist_item()` is called from:

- `create`, on `templates.filtered("pack_ok")` (non-packs can never own an item, and
  product creation is hot enough that one search each is worth skipping)
- `write`, when `pack_ok`, `discount` or `pack_discount` is in vals

Item state is derived from `_pack_effective_discount()`, which returns 0 unless
`pack_ok and discount` — that is what deletes the item when either is switched off.
A component price change moves `list_price`, the item's *base*, but not `percent_price`,
so it needs no resync.

Two vals rewrites in `write`, both to keep a switch and the value it controls consistent:
`pack_ok = False` forces `pack_price_auto = False` (otherwise `_check_pack_price_auto`
aborts the save and the item stays), and `discount = False` forces `pack_discount = 0.0`.
`_compute_pack_totals` gates on `discount` anyway, so a stale percentage arriving by import
still shows and prices as no discount.

## Invariants — break these and something silently rots

- A pack with **no** components is skipped by the sync. Otherwise ticking the flag on an
  existing product zeroes its price.
- Packs with `discount` off must end up with **no** item in the Packs pricelist. Non-auto
  packs may now own one — that changed when `discount` split off from `pack_price_auto`.
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
- `../custom_pack_website`'s confirm-time section surgery is now dead code outright — no pack
  ever gets child lines to move. Left in place; deleting it is a separate call.

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
`discount` on + `pack_discount` 10% → 630 on the Packs pricelist, margin after discount 280
(44.44%), one order line.

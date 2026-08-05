# pack_pricing — manual test book

Covers every branch reachable from the UI and the ORM. Automated coverage lives in
`tests/test_pack_pricing.py`; cases below marked **[auto]** are already asserted there
and only need a re-check when the UI changes.

```bash
odoo -d YOURDB -i pack_pricing --test-enable --test-tags /pack_pricing --stop-after-init
```

## Fixture

Create once, reuse for everything below. Keep all products **Type = Goods, not
storable** (`consu`) — see INV-3.

| Product | Cost | Sales price | Notes |
|---|---|---|---|
| `Component B` | 100 | 200 | plain product |
| `Component C` | 50 | 100 | plain product |
| `Pack A` | — | — | Is a pack ✓, Auto Pack Pricing ✓, lines: 2 × B, 3 × C |
| `Pack OCA` | — | — | Is a pack ✓, Auto Pack Pricing ✗, same lines |
| `Plain` | 10 | 20 | not a pack |

Reference numbers for Pack A: cost **350**, sale **700**, margin **350** (50%),
at 10% discount → final **630**, margin after discount **280**.

---

## 1. Install / upgrade

| ID | Steps | Expected |
|---|---|---|
| INS-1 | Install `pack_pricing` | Installs with `sale_product_pack` + `website_sale`. No warnings in log. |
| INS-2 | Sales ▸ Configuration ▸ Pricelists | Pricelist **Packs** exists, sequence 1, **not selectable**, website = default website. |
| INS-3 | Rename Packs pricelist, then upgrade the module | Rename survives (`noupdate="1"`). |
| INS-4 | Uninstall | No traceback. Packs pricelist and its items removed with it. |
| INS-5 | Install on a DB with existing packs | No existing pack changes price (flag defaults off). |

## 2. The `pack_price_auto` flag

| ID | Steps | Expected |
|---|---|---|
| FLG-1 **[auto]** | On `Plain`, tick Auto Pack Pricing | `ValidationError`: "Auto Pack Pricing only applies to pack products." |
| FLG-2 | On `Pack A` (auto on), untick **Is a pack** and save | Same ValidationError — untick Auto Pack Pricing *first*. Document this order for users. |
| FLG-3 | Untick auto, then untick Is a pack, save | Saves. Pricelist item gone (see PL-5). |
| FLG-4 | New pack, no components, list price 500, tick auto, save | List price stays **500** — empty packs are skipped by the sync. **[auto]** |
| FLG-5 | On the FLG-4 pack, add 2 × B and save | List price jumps to 400, cost 200. Manual 500 is overwritten as soon as a component exists. |
| FLG-6 | On `Pack A`, delete **all** pack lines, save | Prices **stay at 700 / 350** — sync skips empty packs, it does not zero them. Known and intended. |
| FLG-7 | Untick auto on `Pack A`, save, re-tick, save | Price returns to 700/350. No duplicate pricelist item. |
| FLG-8 | With auto on, try to edit Sales Price / Cost on the General tab | Both readonly. |
| FLG-9 | With auto off | Both editable, no roll-up happens, Pack tab margin columns still display. |
| FLG-10 | Write `list_price = 1` on `Pack A` via ORM/import while auto on | Accepted, then re-overwritten to 700 on the next sync (any pack-line or component change). Not a bug — the roll-up owns the field. |

## 3. Component roll-up (`product.pack.line`)

| ID | Steps | Expected |
|---|---|---|
| CMP-1 **[auto]** | Open Pack A ▸ Pack tab | Per line: Cost, Sale Price, Cost Subtotal, Sale Subtotal, Margin, Margin (%). Column footers sum Cost=350, Sales Price=700, Margin=350. |
| CMP-2 | Change qty of B from 2 to 4 | Line subtotals 400/800; pack list price 1100, cost 500. |
| CMP-3 | Set line discount (`sale_discount`) 50% on B | B sale subtotal 200 (cost subtotal unchanged at 200), margin 0, margin % = 0. Pack sale 500. |
| CMP-4 | `sale_discount` = 100 on B | B sale subtotal 0, margin −200, margin % = 0 (guarded division). |
| CMP-5 | Quantity 0 on a line | Subtotals 0, margin 0, no division error. |
| CMP-6 | Component with sales price 0 and cost 0 | Line margin % = 0, no error. |
| CMP-7 | Component whose cost > sale price | Negative margin displayed, pack margin drops accordingly. Nothing blocks the save. |
| CMP-8 | Delete a pack line | Pack totals refresh immediately after save. |
| CMP-9 | Add the same component twice as two lines | Both lines counted; totals are the sum. |
| CMP-10 | Add a *variant* of a component | Uses that variant's own cost/price. |
| CMP-11 | Archive a component, reopen the pack | Line and totals unchanged (archiving is not deletion). Note it in release notes if unwanted. |
| CMP-12 | Try to add Pack A as its own component | Blocked by `product_pack`'s recursion guard. |

## 4. Sync triggers

Each of these must refresh the pack **on save**, without reopening the form.

| ID | Trigger | Expected |
|---|---|---|
| SYN-1 **[auto]** | Change `Component B` sales price to 300 **from the product template form** | Pack A list price 900. |
| SYN-2 | Change `Component B` cost to 150 from the **template** form | Pack A cost 450. |
| SYN-3 | Change `Component B` cost from the **variant** form (Variants ▸ open variant) | ⚠️ Verify. `standard_price` is a real field on `product.product` and does not go through `product.template.write`, so the pack may not refresh until something else on the pack is saved. Record actual behaviour; if it does not refresh, that is a known gap, not a regression. |
| SYN-4 | Create / write / unlink a pack line | Parent pack refreshed via `_sync_parent_packs()`. |
| SYN-5 | Component used by two packs, change its price | **Both** packs refresh. |
| SYN-6 | Component used by a non-auto pack, change its price | Non-auto pack untouched. |
| SYN-7 | Import 50 pack lines at once (CSV) | One refresh, correct totals, no recursion error. |
| SYN-8 | Duplicate Pack A | Copy has its own lines, own totals, and — after its first save with a discount — its **own** pricelist item. |
| SYN-9 | Nested: make Pack A a component of Pack Z (both auto) | Pack Z uses Pack A's *current* stored price. Changing Pack A's components does **not** cascade to Pack Z until Pack Z is saved again. Documented limit. |

## 5. Discount and the Packs pricelist

| ID | Steps | Expected |
|---|---|---|
| PL-1 **[auto]** | Pack A, set discount 10%, save | Price After Discount = 630. One item in Packs pricelist: applied on product, compute = percentage, percent = 10, base = Sales Price, min qty 0. |
| PL-2 **[auto]** | Change discount to 20%, save | The **same** item is updated (still exactly one item), percent 20, price 560. |
| PL-3 **[auto]** | Set discount back to 0, save | Item deleted. |
| PL-4 **[auto]** | Discount 10%, then untick Auto Pack Pricing | Item deleted. `pack_discount` value is kept on the product but no longer published. |
| PL-5 | Discount 10%, untick auto, untick Is a pack | Item deleted. |
| PL-6 | Re-tick auto with `pack_discount` still 10 | Item recreated with 10%. |
| PL-7 | Set discount on `Pack OCA` (auto off) | Value stored, **no** pricelist item created. This is the #1 "the discount doesn't work" support ticket. |
| PL-8 **[auto]** | Discount −5 | ValidationError. |
| PL-9 **[auto]** | Discount 120 | ValidationError. |
| PL-10 | Discount exactly 100 | ValidationError (100 excluded). |
| PL-11 | Discount 99.99 | Accepted, final price 0.07. |
| PL-12 | Delete Pack A entirely | Its pricelist item is gone too (no orphan pointing at a dead product). |
| PL-13 | Manually add a second item for Pack A in the Packs pricelist, then re-save the pack | The module updates the one it finds first; the manual duplicate is not cleaned. Don't hand-edit the Packs pricelist. |
| PL-14 | Log in as a **Sales / User** (not admin), edit a pack discount, save | Saves without AccessError (items written with `sudo()`). |
| PL-15 | Check `_get_product_price` in a shell for the Packs pricelist | 630.0 for Pack A at qty 1 with 10%. **[auto]** |

## 6. Margins in the Pack tab

| ID | Steps | Expected |
|---|---|---|
| MRG-1 | Discount 0 | The **Margin** group is hidden; only Pack Discount + Price After Discount visible. |
| MRG-2 | Discount 10 | Margin group appears: Before Discount **350**, Margin After Discount **280**. Confirms discount burns margin faster than its own % (10% of 700 = 70, off a 350 margin). |
| MRG-3 | Discount high enough that cost > final price (e.g. 60% → 280 < 350) | Margin After Discount negative (−70). Displayed, not blocked. |
| MRG-4 | Pack with 0 sale total | Margin % = 0, no ZeroDivision. |
| MRG-5 | Read `pack_total_cost` / `pack_total_sale` / `pack_margin_percent` via shell | Computed correctly even though no view renders them. |

## 7. Selling — sale order

| ID | Steps | Expected |
|---|---|---|
| SO-1 **[auto]** | New quotation, no pricelist / default pricelist, add Pack A qty 1 | **One** order line. Unit price 700. No component lines. |
| SO-2 **[auto]** | Same with pricelist = Packs, discount 10% | One line, unit price **630**. |
| SO-3 | Qty 5 with Packs pricelist | Unit price 630, subtotal 3150, still one line. |
| SO-4 | Add `Pack OCA` (auto off) | OCA behaviour unchanged: component lines expanded per its Pack Display Type. Regression check. |
| SO-5 | Confirm the SO-1 order | One delivery move (or none, for `consu` non-storable), one invoice line, correct amount. |
| SO-6 | Change qty on a confirmed auto-pack line | No component lines appear or need re-syncing. |
| SO-7 | Customer with their **own** pricelist set on the partner | Partner pricelist wins over Packs — the pack discount does **not** apply. Documented limit, verify it is at least consistent between quotation and website. |
| SO-8 | Change the pack's components **after** an order is confirmed | Order line price unchanged (snapshot at order time). Expected. |

## 8. Pack Display Type matrix (auto = ON)

For each combination, price must be **700** (or 630 with the Packs pricelist) and the
order must have **one** line. `_is_pack_to_be_handled()` must return `False` throughout.

| ID | Pack Display Type | Component Price | Expected |
|---|---|---|---|
| PDT-1 | Detailed | Ignored | 700 / one line |
| PDT-2 | Detailed | Totalized | 700 / one line |
| PDT-3 | Detailed | Detailed per line | 700 / one line |
| PDT-4 **[auto]** | Non detailed | (n/a) | 700 / one line, 630 on Packs pricelist |

With auto **OFF**, the same matrix must reproduce stock OCA behaviour — spot-check
PDT-1 and PDT-4 with `Pack OCA`.

## 9. Website shop

| ID | Steps | Expected |
|---|---|---|
| WEB-1 | Publish Pack A, browse the shop **logged out** | Product page shows 630 (strikethrough 700 if the theme does that). |
| WEB-2 | Add to cart, logged out | Cart has **one** line at 630. No component lines. |
| WEB-3 | Checkout as public → order created | One order line, 630. |
| WEB-4 | Log in as a portal user **without** a pricelist on the partner | 630. |
| WEB-5 | Log in as a portal user **with** a pricelist on the partner | Partner pricelist wins, discount likely not applied. **Known limit** — do not file as a bug. |
| WEB-6 | `Pack OCA` on the website | Unchanged OCA rendering. |
| WEB-7 | Multi-website DB | Packs pricelist is bound to the *default* website only. Second website does not get the discount. Verify and document. |

## 10. Invariants / regression traps

| ID | Check | Why |
|---|---|---|
| INV-1 | No non-auto pack ever has an item in the Packs pricelist. Query `product.pricelist.item` on that pricelist and cross-check every `product_tmpl_id` has `pack_ok and pack_price_auto`. | The whole discount contract. |
| INV-2 | An auto pack with zero components is never zeroed. | FLG-4 / FLG-6. |
| INV-3 | Set an auto pack to **storable** with AVCO/FIFO and on-hand stock, then change a component's cost | Stock revaluation journal entries are created by the `standard_price` write. Keep auto packs `consu`. If a customer needs storable auto packs, that is a design conversation, not a bugfix. |
| INV-4 | Second company, different currency | Roll-up runs in the pack's own currency; `standard_price` is company-dependent so cost is per company. Verify no cross-company leak. |
| INV-5 | Sync re-entry | Save a pack repeatedly / change a component that is inside two packs sharing a component. No infinite loop, no `RecursionError` (guarded by the `pack_price_sync` context key). |
| INV-6 | Rounding | Components 3 × 33.33 with 3 decimals of Product Price precision — totals respect the decimal precision, no 0.001 drift between the list price and the sum shown in the tab. |

## 11. UI / i18n

| ID | Check |
|---|---|
| UI-1 | Pack tab list shows the six added columns; `Margin (%)` is an optional column and can be hidden. |
| UI-2 | Column sums render under Cost, Sales Price, Margin. |
| UI-3 | Pack line **form** view (open a line in a dialog) shows the same six fields. |
| UI-4 | The muted helper paragraph under Pack Discount only shows when Auto Pack Pricing is ticked. |
| UI-5 | Switch user language to French: `Auto Pack Pricing`, `Pack Discount (%)`, `Margin After Discount`, both error messages are translated (`i18n/fr.po`). |
| UI-6 | Error messages render the `%` sign literally, not `%%` ("between 0% (included) and 100% (excluded)"). |
| UI-7 | Product form loads with no JS console error on a non-pack product (the Pack tab is hidden). |

---

## Regression sign-off checklist

Minimum set before shipping a change: FLG-1, FLG-4, FLG-6, CMP-1, SYN-1, SYN-5,
PL-1, PL-3, PL-4, PL-7, SO-1, SO-2, SO-4, PDT-4, WEB-2, INV-1.

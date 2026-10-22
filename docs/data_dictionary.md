# Data dictionary

File: `data/processed/heel_listings_clean.csv` (780 rows, UTF-8 with BOM). Built by `scripts/prepare_dashboard_data.py`; changes are in `docs/decision_log.md`.

| Column | Type | Nulls | Description | Source |
|---|---|---|---|---|
| itemId | text | 0 | eBay Browse API item id (unique key). | raw |
| title | text | 0 | Listing title as scraped. | raw |
| category | text | 0 | eBay category (raw `specificCategory`): Heels, Pumps, Bridal Shoes, Women's Vintage Shoes, Women's Boots, Sandals, Boots. | raw, renamed |
| price | number (USD) | 0 | Asking price, not a sold price. | raw |
| condition | text | 0 | eBay condition label, unchanged (11 values). | raw |
| condition_group | text | 1 | New / Pre-owned - Excellent / Good / Fair / Pre-owned (unspecified); null for 'Unspecified'. | derived from condition |
| size | number | 153 | US shoe size, 4-13, half sizes as .5. Null if absent, EU-only, or out of range. | derived from title |
| size_width | text | 669 | Width letters from the title (A, AA, B, C, D, E, EE, M, N, W, WW). | derived from title |
| brand | text | 245 | Brand from a reference list, longest match first; sub-lines merged into parent; null if none. | derived from title |
| color | text | 143 | Base color group; 'Multicolor' if 2+ color words; null if none. | derived from title |
| material | text | 303 | Material keyword; 'Multimaterial' if 2+ words; null if none. | derived from title |
| itemURL | text | 0 | eBay Browse API endpoint for the item (not a browsable web page). | raw |
| imageURL | text | 0 | Thumbnail image URL on i.ebayimg.com. | raw |

Known limitations: prices are active asking prices; brand/color/material are keyword matches from titles (possible false positives, e.g. 'Brocade', 'Barbie', 'Gap'); size is US only (EU sizes are not converted).

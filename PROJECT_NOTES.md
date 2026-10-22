# Vintage Heel Price Predictor: Project Notes

Last updated: 2026-10-21

Context document for anyone (including AI coding tools) picking up this project. It records what has been built, what was decided and why, known problems, and what comes next.

## Goal

Help consumers estimate a fair price for a heel (especially vintage) from its attributes: brand, size, color, material, style, and condition. A photo-based price estimate is the planned next phase. The project is also a data analyst / data science portfolio piece.

## Development process

I use AI tools (Claude) throughout this project to work more efficiently and productively, and I want that to be clear to anyone reading this repo.

- **While building:** Claude acted as a tutor and pair-programmer. It explained concepts (OAuth, pagination, regex, fuzzy matching), suggested approaches and scaffolds, and helped review and debug code. Commit history reflects the real iteration, including mistakes and fixes.
- **For dashboard preparation:** I use Claude Code to automate repetitive data-prep work, under the rules below.
- **My role:** I define the question, choose data sources and cleaning rules, run and test the code, validate results against real data (spot checks, null counts, sample sizes), and make every data decision.

Rules for AI-assisted data prep:
1. Start in plan mode and show evidence (counts, examples) before proposing changes.
2. Ask me before any decision that changes the data: dropping rows, imputing nulls, merging categories, handling outliers, renaming or removing columns.
3. Write cleaning logic as re-runnable code, not manual edits.
4. Log every change in `docs/decision_log.md`: what, why, rows affected.
5. I review every diff before it is committed.

## Repo layout

```
scrapers/    ebay_scraper.py (HTML, blocked), depop_scraper.py (blocked), ebay_api_scraper.py (working)
notebooks/   01_eda.ipynb (loading, cleaning, feature extraction, first charts)
data/raw/    scraped CSVs (gitignored); data/images/ downloaded thumbnails (gitignored)
```

Credentials live in `.env` (gitignored): `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`.

## Data sources tried

| Source | Result |
|---|---|
| eBay search pages (requests + BeautifulSoup) | Blocked (HTTP 403) despite header and session changes |
| TheRealReal | Cloudflare human-verification challenge, even in a normal browser. Dropped |
| Depop (internal JSON search API found via browser Network tab) | Scraper built with cursor pagination, but Cloudflare challenge page returned instead of JSON. No Depop data collected |
| **eBay Browse API (OAuth client credentials)** | **Working.** Offset pagination, `limit=50`. Produced 1,162 rows |
| Vinted, ThredUp, Poshmark, Etsy, Facebook Marketplace | Not attempted. Expect similar bot protection on some |

## Dataset

Source file: `data/raw/ebay_api_listings.csv` (1,162 rows after collection).

Collected fields: `itemId`, `title`, `specificCategory`, `price`, `itemURL`, `condition`, `imageURL`, `image_local_path`.

Fields derived from `title` in `01_eda.ipynb`:
- **size**: regex, three tiers: explicit "Size N", then number plus width letters (7B, 7AA, 8.5N), then a bare small number that is not a decade like 80's. Fractions like "6 1/2" are normalized to 6.5. About 80 of 1,162 have no size.
- **brand**: case-insensitive reference-list lookup, then `rapidfuzz` matching (threshold 85) to consolidate typos and spacing variants. About 130 nulls remain.
- **colors**: keyword list; two or more matches returns "Multicolor". Grouped into base colors via a `color_groups` mapping.
- **materials**: keyword list, same approach.

## Cleaning decisions so far

- Removed rows with unrelated categories (men's shoes) by keeping only an explicit list of valid `specificCategory` values.
- Left unmatched size and brand as null (judged to be genuinely absent from titles).

## First findings (descriptive only)

Counts matter: many group averages rest on very few listings.
- Brand: PRADA averages about $276 on 11 listings. Most higher averages (Miu Miu, Louis Vuitton, Jimmy Choo) are single listings and not meaningful.
- Color: Black (150) and Multicolor (140) dominate. Pink averages about $104 on 17 listings; Tan about $43 on 33.
- Material: Leather (210) is the largest group. Satin averages about $78 (22) and Velvet about $75 (15).

## Known issues and limitations

1. **Prices are likely asking prices, not sold prices.** The Browse API search returns active listings. A "what should I pay" model trained on asking prices is biased. Verify and state this in any write-up.
2. **Substring false matches.** "lei" matched inside "Klein". Color and material words may match inside longer words (for example "red" inside "embroidered"), which may inflate Multicolor and distort Red. Fix: word-boundary matching (`\b`) for all keyword lists, then re-check.
3. **Non-heel contamination.** At least one snowboard boot slipped in via the "vintage boots" search term. Needs a title or category filter.
4. **Rare brands.** Many brands appear once. For modeling, group rare brands into "Other" or add a luxury-brand flag.
5. **Check suspicious brand hits**, for example "Apple Bottoms" at $360.
6. **Short or generic brand names** (LEI, Rosa, Connie, Andrea, Allure, Socialite, Bijou) are false-positive risks. Review matches.
7. **Style and heel height** were on the original wishlist but are not yet extracted.

## Next steps

1. Fix word-boundary matching for brand, color, and material; re-run and re-check null counts and samples.
2. Filter non-heel listings and review flagged brand matches.
3. Prepare a dashboard-ready dataset: tidy CSV in `data/processed/` plus a short data dictionary, with every change logged in `docs/decision_log.md`.
4. Build the Power BI or Tableau dashboard from the processed CSV.
5. Next phase: scrape a lot more data through the working eBay Browse API (broader search terms, images included, since 1,162 rows is small for an image model), then build an image-based machine learning model that estimates a shoe's price from a photo.
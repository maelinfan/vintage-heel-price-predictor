"""Prepare the heel listings for a Power BI / Tableau dashboard.

Re-runnable pipeline that ports the cleaning logic from notebook/01_eda.ipynb and
applies the decisions recorded in docs/decision_log.md (all user-approved).

    python scripts/prepare_dashboard_data.py            # build outputs
    python scripts/prepare_dashboard_data.py --review   # print candidates for decisions, write nothing
                                                        # (except a blank config/boots_review.csv template)

Outputs
    data/processed/heel_listings_clean.csv   tidy dataset (UTF-8 with BOM)
    docs/decision_log.md                     what / why / rows affected for every step
    docs/data_dictionary.md                  column dictionary
Input
    data/raw/heels_listings.csv
    config/boots_review.csv                  keep/drop decisions for women's boots without heel info
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heel_vocab import BRANDS, COLOR_GROUPS, COLORS, MATERIALS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "heels_listings.csv"
OUT = ROOT / "data" / "processed" / "heel_listings_clean.csv"
LOG = ROOT / "docs" / "decision_log.md"
DICT = ROOT / "docs" / "data_dictionary.md"
BOOTS_REVIEW = ROOT / "config" / "boots_review.csv"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --------------------------------------------------------------------------- decisions
BASE_CATEGORIES = ["Heels", "Bridal Shoes", "Women's Vintage Shoes", "Pumps", "Women's Boots"]

MEN_KIDS = re.compile(r"\b(?:men'?s|mens|men’s|men|male|boys?|unisex|youth|kids?|toddler|children)\b", re.I)
HEEL_WORDS = r"heels?|heeled|stilettos?|pumps?|kitten|block|stack(?:ed)?|cuban"
SANDAL_HEELED = re.compile(rf"\b(?:{HEEL_WORDS}|wedges?|platforms?)\b", re.I)
BOOT_HEELED = re.compile(rf"\b(?:{HEEL_WORDS})\b", re.I)
WOMEN = re.compile(r"\b(?:women'?s|womens|women’s|ladies|womans|woman)\b", re.I)

# Approved drops of items that are not heels (itemId -> reason).
NON_HEEL_DROPS = {
    "v1|168581570901|0": "Shimano snowboarding boots (not a heel)",
    "v1|168585821647|0": "Chanel ballet flats (not a heel)",
    "v1|407115128387|0": "Thom McCan loafers, no heel mentioned",
    "v1|227460666205|0": "Susan Bennis/Warren Edwards loafer, no heel mentioned",
    "v1|147480916729|0": "Bootalino's knee-high boots, no heel mentioned",
}

# Approved later-copy drops (identical title + price). Any other pair stops the run.
APPROVED_DUPLICATE_DROPS = {
    "v1|158096242487|459340279954",
    "v1|407020137768|0",
    "v1|398183728177|666464801639",
}

# Sub-lines merged into the parent brand (approved).
BRAND_MERGE = {
    "Bally Suite": "BALLY",
    "Amalfi Rangoni": "Amalfi",
    "Unisa Keyana": "Unisa",
    "Michelle D Brown": "Michelle D",
    "Boutique 9 BT Joy": "Boutique 9",
    "Circa Joan & David": "Joan & David",
}
# Display casing (approved: all-caps entries to title case; initialisms BCBG, MIA, LEI, KF, JG kept).
BRAND_CASING = {
    "PRADA": "Prada", "BALLY": "Bally", "ZARA": "Zara", "BUMPER": "Bumper", "SPICY": "Spicy",
    "BODEN": "Boden", "BALDAN": "Baldan", "LARIO": "Lario", "IMPO": "Impo",
    "WILD PAIR": "Wild Pair", "TOUCH-UPS": "Touch-Ups",
}

WIDTHS = {"A", "AA", "B", "C", "D", "E", "EE", "M", "N", "W", "WW"}
SIZE_MIN, SIZE_MAX = 4, 13

CONDITION_GROUP = {
    "New with box": "New", "New without box": "New", "New with tags": "New",
    "New without tags": "New", "New with defects": "New",
    "Pre-owned - Excellent": "Pre-owned - Excellent",
    "Gebraucht - Hervorragend": "Pre-owned - Excellent",
    "Pre-owned - Good": "Pre-owned - Good",
    "Pre-owned - Fair": "Pre-owned - Fair",
    "Pre-owned": "Pre-owned (unspecified)",
    "Used": "Pre-owned (unspecified)",
    "Unspecified": None,
}

# --------------------------------------------------------------------------- extraction
BRAND_PATTERNS = [(b, re.compile(rf"\b{re.escape(b)}\b", re.I)) for b in BRANDS]  # BRANDS is longest-first


def extract_brand(title):
    for brand, pat in BRAND_PATTERNS:
        if pat.search(title):
            brand = BRAND_MERGE.get(brand, brand)
            return BRAND_CASING.get(brand, brand)
    return None


PLURAL_OK = {"Rhinestone", "Sequin"}  # approved: also match "Rhinestones", "Sequins"


def _word_pattern(word):
    plural = "s?" if word in PLURAL_OK else ""
    return re.compile(rf"\b{re.escape(word)}{plural}\b", re.I)


COLOR_PATTERNS = [(c, _word_pattern(c)) for c in COLORS]
MATERIAL_PATTERNS = [(m, _word_pattern(m)) for m in MATERIALS]


def _one_or_multi(title, patterns, multi_label):
    found = [w for w, p in patterns if p.search(title)]
    if len(found) == 1:
        return found[0]
    return multi_label if found else None


def extract_color(title):
    label = _one_or_multi(title, COLOR_PATTERNS, "Multicolor")
    return COLOR_GROUPS.get(label, label) if label else None


def extract_material(title):
    return _one_or_multi(title, MATERIAL_PATTERNS, "Multimaterial")


# old (notebook) substring versions, used only to report what changed
def _old_substring(title, words, multi_label):
    found = [w for w in words if w.lower() in title.lower()]
    if len(found) == 1:
        return found[0]
    return multi_label if found else None


def old_color(title):
    label = _old_substring(title, COLORS, "Multicolor")
    return COLOR_GROUPS.get(label, label) if label else None


def old_material(title):
    return _old_substring(title, MATERIALS, "Multimaterial")


FRACTION = re.compile(r"(\d+)\s*(?:and\s*)?1/2", re.I)
NUM = r"\d{1,2}(?:\.\d+)?"
NOT_UNIT = r"(?!\s*(?:\"|”|in\b|inch|cm\b|mm\b))"  # approved: a number followed by an inch/cm mark is a measurement, not a size
US_BEFORE = re.compile(rf"\bUS\s*(?:size\s*|sz\.?\s*)?({NUM})", re.I)
US_AFTER = re.compile(rf"(?<![\w.]){'(' + NUM + ')'}\s*US\b", re.I)
BARE_NUM = re.compile(rf"(?<![\w.$#])({NUM})(?![\w.\"”]|'?s\b|\s*(?:in\b|inch|cm\b|mm\b))")


def normalize_fractions(title):
    return FRACTION.sub(lambda m: str(float(m.group(1)) + 0.5), title)


def notebook_size_token(title):
    """Notebook's 4-tier extractor (cell 20) after the fraction fix. Returns matched token or None."""
    m = re.search(rf"size\s*({NUM}[A-Z]{{0,2}})", title, re.I)
    if m:
        return m.group(1)
    m = re.search(rf"\b{NUM}[A-Z]{{1,2}}\b{NOT_UNIT}", title)
    if m:
        return m.group()
    m = re.search(rf"\b{NUM}\b(?!'?s){NOT_UNIT}", title)
    return m.group() if m else None


def _split_token(token):
    m = re.fullmatch(rf"({NUM})([A-Za-z]{{0,2}})", token)
    num = float(m.group(1))
    width = m.group(2).upper()
    return num, (width if width in WIDTHS else None)


def extract_size(title):
    """Return (size, size_width, how). size is a US number in [SIZE_MIN, SIZE_MAX] or None."""
    t = normalize_fractions(title)
    token = notebook_size_token(t)
    if token is not None:
        num, width = _split_token(token)
        if SIZE_MIN <= num <= SIZE_MAX:
            return num, width, "notebook"
        primary = token
    else:
        primary = None
    # primary missing/out of range (EU size, heel height...): look for an explicit or second US number
    for pat in (US_BEFORE, US_AFTER):
        for m in pat.finditer(t):
            n = float(m.group(1))
            if SIZE_MIN <= n <= SIZE_MAX:
                return n, None, "us_explicit"
    if primary is not None:
        for m in BARE_NUM.finditer(t):
            n = float(m.group(1))
            if m.group(1) != primary and SIZE_MIN <= n <= SIZE_MAX:
                return n, None, "us_second_number"
    return None, None, ("out_of_range" if primary is not None else "none")


# --------------------------------------------------------------------------- pipeline
class Log:
    def __init__(self):
        self.steps = []

    def add(self, title, what, why, before, after, affected, detail=""):
        self.steps.append(dict(title=title, what=what, why=why, before=before, after=after,
                               affected=affected, detail=detail))


def md_table(df, cols):
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("(null)" if pd.isna(r[c]) else str(r[c]).replace("|", "\\|") for c in cols) + " |")
    return "\n".join(lines)


def build(review):
    log = Log()
    raw = pd.read_csv(RAW)
    df = raw.copy()
    n0 = len(df)
    assert df["itemId"].is_unique
    log.add("1. Load raw", f"Read `{RAW.relative_to(ROOT)}`.", "Starting point.", n0, n0, 0)

    # ---- 2. scope
    cat = df["specificCategory"]
    men = df["title"].str.contains(MEN_KIDS)
    base = cat.isin(BASE_CATEGORIES)
    sandals = (cat == "Sandals") & df["title"].str.contains(SANDAL_HEELED) & ~men
    boots_cat = cat == "Boots"
    boots_heel = boots_cat & df["title"].str.contains(BOOT_HEELED) & ~men
    boots_cand = boots_cat & df["title"].str.contains(WOMEN) & ~men & ~df["title"].str.contains(BOOT_HEELED)

    if BOOTS_REVIEW.exists():
        rev = pd.read_csv(BOOTS_REVIEW)
    else:
        rev = df.loc[boots_cand, ["itemId", "title"]].assign(decision="")
        if review:
            BOOTS_REVIEW.parent.mkdir(exist_ok=True)
            rev.to_csv(BOOTS_REVIEW, index=False, encoding="utf-8-sig")
    if review:
        print(f"\n=== Women's boots without heel info: {boots_cand.sum()} candidates "
              f"(fill `decision` = keep/drop in {BOOTS_REVIEW.relative_to(ROOT)}) ===")
        for _, r in df.loc[boots_cand].iterrows():
            print(f"  {r.itemId:32s} ${r.price:<8} {r.title}")
    decisions = rev.set_index("itemId")["decision"].astype(str).str.strip().str.lower()
    if not review:
        missing = set(df.loc[boots_cand, "itemId"]) - set(decisions[decisions.isin(["keep", "drop"])].index)
        if missing:
            sys.exit(f"{len(missing)} boots in {BOOTS_REVIEW.name} have no keep/drop decision; run --review.")
    boots_keep = df["itemId"].isin(decisions[decisions == "keep"].index) & boots_cand

    keep = base | sandals | boots_heel | boots_keep
    scope_detail = (
        f"- Base categories ({', '.join(BASE_CATEGORIES)}): {int(base.sum())}\n"
        f"- Heeled Sandals added (title has heel/heels/heeled/stiletto/kitten/block/pump/stacked/cuban or wedge/platform, "
        f"men's/unisex/kids words excluded): {int(sandals.sum())} of {int((cat == 'Sandals').sum())}\n"
        f"- Boots added with explicit heel words, no men's/unisex/kids words: {int(boots_heel.sum())} of {int(boots_cat.sum())}\n"
        f"- Women's boots without heel info ({int(boots_cand.sum())} reviewed one by one): kept {int(boots_keep.sum())}, "
        f"dropped {int((boots_cand & ~boots_keep).sum())} (`config/boots_review.csv`)\n"
        f"- Excluded: {n0 - int(keep.sum())} rows (all other Sandals/Boots, Comfort Shoes, Men's/Western/Children's, Socks, "
        f"Slippers, Flats, Casual Shoes, Bags, Collectibles)"
    )
    df = df[keep].copy()
    log.add("2. Scope", "Keep heel-type listings: base categories + heeled sandals + women's heeled boots.",
            "Notebook kept only 5 categories (656 rows) and dropped heeled sandals/boots; user chose to include them.",
            n0, len(df), n0 - len(df), scope_detail)

    # ---- 3. non-heel drops
    nb = len(df)
    drop_ids = [i for i in NON_HEEL_DROPS if i in set(df["itemId"])]
    detail = "\n".join(f"- `{i}`: {NON_HEEL_DROPS[i]} ({df.loc[df.itemId == i, 'title'].iloc[0]})" for i in drop_ids)
    df = df[~df["itemId"].isin(drop_ids)]
    log.add("3. Non-heel drops", "Drop listings that are not heels.",
            "Snowboard boots, ballet flats, and loafers/boots with no heel mention; the other 19 borderline "
            "titles (loafer/oxford/bootie *heels*) mention heels and are kept.", nb, len(df), nb - len(df), detail)

    # ---- 4. duplicates
    nb = len(df)
    dup = df.duplicated(["title", "price"], keep="first")
    found = set(df.loc[dup, "itemId"])
    extra = found - APPROVED_DUPLICATE_DROPS
    if review:
        print(f"\n=== Duplicate (title, price) later copies: {len(found)} ===")
        for i in sorted(found):
            print("  ", i, "(approved)" if i in APPROVED_DUPLICATE_DROPS else "(NOT YET APPROVED)", df.loc[df.itemId == i, "title"].iloc[0])
    elif extra:
        sys.exit(f"Unapproved duplicate drops: {sorted(extra)} - decide, then add to APPROVED_DUPLICATE_DROPS.")
    df = df[~df["itemId"].isin(APPROVED_DUPLICATE_DROPS & found)]
    log.add("4. Duplicates", "Drop later copy of listings with identical title and price.",
            "Multi-variation listings repeat the same title/price; user approved dropping the later copies. "
            "Note: the second pair has different item numbers and could be two physical items.",
            nb, len(df), nb - len(df), "\n".join(f"- `{i}`" for i in sorted(APPROVED_DUPLICATE_DROPS & found)))

    df = df.reset_index(drop=True)

    # ---- 5. size
    sz = df["title"].apply(extract_size)
    df["size"] = sz.str[0]
    df["size_width"] = sz.str[1]
    how = sz.str[2]
    fixed_frac = df[df["title"].apply(lambda t: bool(FRACTION.search(t)))]
    size_detail = (
        f"- Valid US size kept from notebook logic: {int((how == 'notebook').sum())}\n"
        f"- EU/other number replaced by US size found in title (explicit 'US n': {int((how == 'us_explicit').sum())}, "
        f"second number 4-13: {int((how == 'us_second_number').sum())})\n"
        f"- Set to null, number outside {SIZE_MIN}-{SIZE_MAX} (EU-only sizes, heel heights like 3\", '3D'): {int((how == 'out_of_range').sum())}\n"
        f"- Null, no size found: {int((how == 'none').sum())}\n"
        f"- Fraction fix (`6 1/2` -> 6.5) applied to {len(fixed_frac)} titles\n"
        f"- `size_width` filled for {int(df['size_width'].notna().sum())} rows (A, AA, B, C, D, E, EE, M, N, W, WW)\n"
    )
    changed = df[how.isin(["us_explicit", "us_second_number"])][["itemId", "title", "size"]]
    if len(changed):
        size_detail += "\nRows where the US size was taken instead of the EU number:\n\n" + md_table(changed, ["itemId", "title", "size"])
    log.add("5. Size", "Re-extract size as a numeric US size plus a separate width column.",
            "Notebook size was text mixing US, EU, widths and heel heights; fraction regex had a bug (`s+` instead of `\\s+`).",
            len(df), len(df), int(how.isin(["us_explicit", "us_second_number", "out_of_range"]).sum()), size_detail)
    if review:
        print("\n=== Size re-extraction (EU -> US) ===")
        for _, r in changed.iterrows():
            print(f"  {r['size']:<5} {r['title']}")
        suspicious = df[(how == "notebook") & df["title"].str.contains(r'(?<![\d.])[4-9]\s*(?:"|”|in\b|inch)', regex=True)]
        print(f"\n=== In-range sizes where title also has a 4-9 inch heel height (possible heel height mistaken for size): {len(suspicious)} ===")
        for _, r in suspicious.iterrows():
            print(f"  size={r['size']:<5} {r['title']}")

    # ---- 6. brand
    df["brand"] = df["title"].apply(extract_brand)
    log.add("6. Brand", "Extract brand from title with a deterministic, longest-match-first lookup; merge sub-lines into the parent brand; normalise casing.",
            "Notebook iterated `list(set(brands))` (random order per run). Merges: "
            + ", ".join(f"{k}->{v}" for k, v in BRAND_MERGE.items())
            + ". Casing: " + ", ".join(f"{k}->{v}" for k, v in BRAND_CASING.items()) + ". Unmatched titles stay null; "
            "possible false positives (e.g. Brocade, Barbie, Gap) are left in as decided.",
            len(df), len(df), int(df["brand"].notna().sum()),
            f"- Brand found: {int(df['brand'].notna().sum())}; null: {int(df['brand'].isna().sum())}; distinct brands: {df['brand'].nunique()}")
    # (the notebook's rapidfuzz step only re-matched names that were already exact list entries)

    # ---- 7. color / material
    df["color"] = df["title"].apply(extract_color)
    df["material"] = df["title"].apply(extract_material)
    for col, old_fn, name in (("color", old_color, "Color"), ("material", old_material, "Material")):
        old = df["title"].apply(old_fn)
        diff = df[old.fillna("") != df[col].fillna("")].assign(old=old[old.fillna("") != df[col].fillna("")])
        detail = f"- {name} null: {int(df[col].isna().sum())}\n- Labels changed vs substring matching: {len(diff)}\n"
        if len(diff):
            detail += "\n" + md_table(diff.rename(columns={col: "new"}), ["itemId", "title", "old", "new"])
        log.add(f"7. {name}", f"Match {name.lower()} keywords with word boundaries.",
                "Substring matching hit inside longer words (Embroidered->Red, Crochet->Croc, Wooden->Wood, Furstenberg->Fur). "
                "Strict `\\b`; the only plurals allowed are Rhinestones and Sequins (approved).",
                len(df), len(df), len(diff), detail)
    if review:
        for words, label in ((COLORS, "colors"), (MATERIALS, "materials")):
            lenient = [(w, re.compile(rf"\b{re.escape(w)}(?:s|es|ed)\b", re.I)) for w in words]
            hits = [(t, [w for w, p in lenient if p.search(t)]) for t in df["title"]]
            hits = [(t, w) for t, w in hits if w]
            print(f"\n=== Titles where a plural/'-ed' form of a {label} word appears (strict \\b ignores these): {len(hits)} ===")
            for t, w in hits:
                print("  ", w, "|", t)

    # ---- 9. condition
    unknown = set(df["condition"]) - set(CONDITION_GROUP)
    assert not unknown, f"Unmapped condition values: {unknown}"
    df["condition_group"] = df["condition"].map(CONDITION_GROUP)
    cg = df["condition_group"].value_counts(dropna=False).to_string()
    log.add("9. Condition", "Add `condition_group`; `condition` is unchanged.",
            "11 raw eBay values (incl. German 'Gebraucht - Hervorragend') are too granular for a slicer. "
            "Mapping: " + "; ".join(f"{k}->{v}" for k, v in CONDITION_GROUP.items()),
            len(df), len(df), int((df["condition"] != df["condition_group"]).sum()), f"```\n{cg}\n```")

    # ---- 10. columns
    df = df.rename(columns={"specificCategory": "category"})
    cols = ["itemId", "title", "category", "price", "condition", "condition_group", "size", "size_width",
            "brand", "color", "material", "itemURL", "imageURL"]
    df = df[cols]
    log.add("10. Columns", "Drop `image_local_path`; rename `specificCategory`->`category`; new columns `condition_group`, "
            "`size_width`; `colors`->`color`, `materials`->`material`.",
            "`image_local_path` is an absolute path on one PC. Snake-case names for dashboard fields. "
            "`itemURL` is kept as-is (an eBay API URL, not a browsable page).",
            len(df), len(df), 0, "Final columns: " + ", ".join(cols))
    log.add("8. Price", "No change.", "All prices kept; no outlier removal (23 listings > $250 are luxury brands, "
            "low prices are plausible).", len(df), len(df), 0)

    # ---- checks
    assert df["itemId"].is_unique
    assert df["price"].notna().all() and (df["price"] > 0).all()
    assert df["size"].dropna().between(SIZE_MIN, SIZE_MAX).all()
    assert df["category"].isin(set(BASE_CATEGORIES) | {"Sandals", "Boots"}).all()
    return df, log, n0


def write_outputs(df, log, n0):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")

    waterfall = [f"- Raw rows: {n0}"]
    for s in log.steps:
        if s["title"][0] in "234":
            waterfall.append(f"- After {s['title']}: {s['after']} ({s['after'] - s['before']:+d})")
    lines = ["# Decision log", "",
             "Generated by `scripts/prepare_dashboard_data.py` (re-run to regenerate). Every decision below was approved by the project owner; "
             "see PROJECT_NOTES.md for process rules.", "",
             "## Row waterfall", *waterfall, f"- Final rows in `{OUT.relative_to(ROOT).as_posix()}`: {len(df)}", ""]
    for s in sorted(log.steps, key=lambda s: int(s["title"].split(".")[0])):
        lines += [f"## {s['title']}", f"**What:** {s['what']}  ", f"**Why:** {s['why']}  ",
                  f"**Rows:** {s['before']} -> {s['after']}; rows affected/changed: {s['affected']}", ""]
        if s["detail"]:
            lines += [s["detail"], ""]
    lines += ["## Null counts in final data", "```", df.isna().sum().to_string(), "```", ""]
    LOG.write_text("\n".join(lines), encoding="utf-8")

    nulls = df.isna().sum()
    desc = {
        "itemId": ("text", "eBay Browse API item id (unique key).", "raw"),
        "title": ("text", "Listing title as scraped.", "raw"),
        "category": ("text", "eBay category (raw `specificCategory`): Heels, Pumps, Bridal Shoes, Women's Vintage Shoes, Women's Boots, Sandals, Boots.", "raw, renamed"),
        "price": ("number (USD)", "Asking price, not a sold price.", "raw"),
        "condition": ("text", "eBay condition label, unchanged (11 values).", "raw"),
        "condition_group": ("text", "New / Pre-owned - Excellent / Good / Fair / Pre-owned (unspecified); null for 'Unspecified'.", "derived from condition"),
        "size": ("number", f"US shoe size, {SIZE_MIN}-{SIZE_MAX}, half sizes as .5. Null if absent, EU-only, or out of range.", "derived from title"),
        "size_width": ("text", "Width letters from the title (A, AA, B, C, D, E, EE, M, N, W, WW).", "derived from title"),
        "brand": ("text", "Brand from a reference list, longest match first; sub-lines merged into parent; null if none.", "derived from title"),
        "color": ("text", "Base color group; 'Multicolor' if 2+ color words; null if none.", "derived from title"),
        "material": ("text", "Material keyword; 'Multimaterial' if 2+ words; null if none.", "derived from title"),
        "itemURL": ("text", "eBay Browse API endpoint for the item (not a browsable web page).", "raw"),
        "imageURL": ("text", "Thumbnail image URL on i.ebayimg.com.", "raw"),
    }
    d = ["# Data dictionary", "", f"File: `{OUT.relative_to(ROOT).as_posix()}` ({len(df)} rows, UTF-8 with BOM). "
         "Built by `scripts/prepare_dashboard_data.py`; changes are in `docs/decision_log.md`.", "",
         "| Column | Type | Nulls | Description | Source |", "|---|---|---|---|---|"]
    for c in df.columns:
        t, ds, src = desc[c]
        d.append(f"| {c} | {t} | {int(nulls[c])} | {ds} | {src} |")
    d += ["", "Known limitations: prices are active asking prices; brand/color/material are keyword matches from titles "
          "(possible false positives, e.g. 'Brocade', 'Barbie', 'Gap'); size is US only (EU sizes are not converted)."]
    DICT.write_text("\n".join(d) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true", help="print candidates for decisions; write no outputs")
    args = ap.parse_args()
    df, log, n0 = build(args.review)
    if args.review:
        print(f"\nReview run complete; would produce {len(df)} rows. Nothing written.")
        return
    write_outputs(df, log, n0)
    print(f"Wrote {OUT} ({len(df)} rows), {LOG.name}, {DICT.name}")


if __name__ == "__main__":
    main()

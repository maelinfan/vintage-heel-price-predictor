"""
eBay sold-listings scraper for vintage heels pricing project.

PURPOSE:
1. Search eBay for sold listings that match a query (e.g. "vintage heels")
2. For each listing found/visited, pull out:
    - price
    - item specifics table (brand, style, heel height, material, color, size, condition, misc. details)
    - title + description text (to catch untagged fields such as 'era')
    - main image URL (and optionally download the image)
3. Save everything to a CSV file in data/raw/

HOW TO RUN
    pip install requests beautifulsoup4 pandas
    python ebay_scraper.py
"""

import time
import csv
import os
import re
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------------------------------------

SEARCH_TERMS = [
    "vintage heels",
    "vintage pumps",
    "vintage stiletto heels",
    "vintage kitten heels",
    "vintage boots",
]

MAX_PAGES_PER_TERM = 3
RATE_LIMIT_SECONDS = 3.0
DOWNLOAD_IMAGES = True
OUTPUT_CSV = "../data/raw/heels_listings.csv"
IMAGE_DIR = "../data/images"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" 
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    )
}

FIELDS = [
    "item_id", "title", "price", "sold_date", "url",
    "brand", "style", "heel_height", "material", "color", "size", "condition",
    "description_snippet", "image_url", "image_local_path",
]

# -----------------------------------------------------------------------------------------------------------
# SEARCH RESULTS PAGE
# -----------------------------------------------------------------------------------------------------------

def build_search_url(query: str, page: int) -> str:
    """
    Builds an eBay search URL filtered to SOLD, completed listings.
    LH_Sold=1 and LH_Complete=1 are eBay's filters for sold items.
    """
    params = {
        "_nkw": query,
        "_sacat": "0",
        "LH_Sold": "1",
        "LH_Complete": "1",
        "_pgn": page,
    }
    return "https://www.ebay.com/sch/i.html?" + urlencode(params)

def get_listing_links(query: str, page: int) -> list[dict]:
    """
    Returns a list of {url, title, price} for each listing on a search results page.
    """
    url = build_search_url(query, page)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    
    results = []
    # Each listing on the results page sits in a <li class="s-item"> card.
    for card in soup.select("li.s-item"):
        link_tag = card.select_one("a.s-item__link")
        title_tag = card.select_one("div.s-item__title")
        price_tag = card.select_one("span.s-item__price")

        if not link_tag or not price_tag:
            continue # Skip if essential info is missing

        item_url = link_tag.get("href", "").split("?")[0] # strip tracking params
        title = title_tag.get_text(strip=True) if title_tag else ""
        price_text = price_tag.get_text(strip=True)

        # Skip the "Shop on eBay" placeholder card eBay sometimes injects
        if "Shop on eBay" in title.lower():
            continue

        results.append({"url": item_url, "title": title, "price_text": price_text})

    return results

def parse_price(price_text: str) -> float | None:
    """Turns '$45.00' or '$40.00 to $60.00' into a single float (uses the low end for ranges)."""
    matches = re.findall(r"[\d,]+\.\d{2}", price_text)
    if not matches:
        return None
    return float(matches[0].replace(",", ""))

# -----------------------------------------------------------------------------------------------------------
# DETAIL PAGE
# -----------------------------------------------------------------------------------------------------------

def parse_item_specifics(soup: BeautifulSoup) -> dict:
    """
    eBay's 'Item specifics' section is usually a series of label/value pairs.
    This function grabs all of them and returns a dict, e.g. {"Brand": "Nine West", "Heel Height": "3 in"}
    so you don't have to hand-write a selector for every possible field.
    """
    specifics = {}
    for row in soup.select("div.ux-labels-values__labels-content"):
        label = row.get_text(strip=True)
        value_container = row.find_next_sibling("div", class_=re.compile("ux-labels-values__values-content"))
        if value_container:
            specifics[label] = value_container.get_text(strip=True)
    return specifics

def guess_era(text: str) -> str | None:
    """
    Simple keyword-based era guesser from title/desscription text.
    Not a finished feature, needs to be refined over time
    """
    text = text.lower()
    decade_match = re.search(r"19[2-9]0s|20[0-2]0s", text)
    if decade_match:
        return decade_match.group(1)
    if "y2k" in text:
        return "2000s (Y2K)"
    if "victorian" in text:
        return "Victorian"
    if "art deco" in text:
        return "Art Deco"
    return None

def get_listing_details(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    
    specifics = parse_item_specifics(soup)

    title_tag = soup.select_one("h1.x-item-title__mainTitle span")
    title = title_tag.get_text(strip=True) if title_tag else ""

    desc_tag = soup.select_one("div.d-item-description") or soup.select_one("div#viTabs_0_is")
    description = desc_tag.get_text(" ", strip=True)[:500] if desc_tag else ""

    image_tag = soup.select_one("img#icImg") or soup.select_one("div.ux-image-carousel img") 
    image_url = image_tag.get("src") if image_tag else None

    combined_text = f"{title} {description}"

    return {
        "title": title,
        "brand": specifics.get("Brand", ""),
        "style": specifics.get("Style", ""),
        "heel_height": specifics.get("Heel Height", ""),
        "material": specifics.get("Upper Material", specifics.get("Material", "")),
        "color": specifics.get("Color", ""),
        "size": specifics.get("Size", ""),
        "condition": specifics.get("Condition", ""),
        "description_snippet": description,
        "image_url": image_url,
        "era_guess": guess_era(combined_text),
    }

def download_image(image_url: str, item_id: str) -> str | None:
    """
    Downloads the image from image_url and saves it to IMAGE_DIR with a filename based on item_id.
    Returns the local file path if successful, or None if failed.
    """
    if not image_url:
        return None
    os.makedirs(IMAGE_DIR, exist_ok=True)
    ext = ".jpg"
    local_path = os.path.join(IMAGE_DIR, f"{item_id}{ext}")
    try:
        resp = requests.get(image_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        return local_path
    except requests.RequestException:
        return None
    
# -----------------------------------------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------------------------------------

def main():
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    write_header = not os.path.exists(OUTPUT_CSV)

    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()

        seen_urls = set()

        for query in SEARCH_TERMS:
            for page in range(1, MAX_PAGES_PER_TERM + 1):
                print(f"Searching for '{query}' page {page}...")
                try:
                    listings = get_listing_links(query, page)
                except requests.RequestException as e:
                    print(f" Search request failed: {e}")
                    continue

                if not listings:
                    print(" No listings found on this page. Stopping this query.")
                    break

                for listing in listings:
                    url = listing["url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    item_id_match = re.search(r"/itm/(\d+)", url)
                    item_id = item_id_match.group(1) if item_id_match else str(hash(url))

                    print(f"  Fetching details for item {item_id}...")
                    time.sleep(RATE_LIMIT_SECONDS)  # Rate limiting
                    

                    try:
                        details = get_listing_details(url)
                    except requests.RequestException as e:
                        print(f"   Detail request failed: {e}")
                        continue

                    image_local_path = ""
                    if DOWNLOAD_IMAGES and details.get("image_url"):
                        time.sleep(RATE_LIMIT_SECONDS)  # Rate limiting for image downloads
                        downloaded = download_image(details["image_url"], item_id)
                        image_local_path = downloaded or ""
                    
                    row = {
                        "item_id": item_id,
                        "title": details["title"] or listing["title"],
                        "price": parse_price(listing["price_text"]),
                        "sold_date": "",  # eBay doesn't always show sold date on the listing page
                        "url": url,
                        "brand": details["brand"],
                        "style": details["style"],
                        "heel_height": details["heel_height"],
                        "material": details["material"],
                        "color": details["color"],
                        "size": details["size"],
                        "condition": details["condition"],
                        "description_snippet": details["description_snippet"],
                        "image_local_path": image_local_path,
                    }
                    writer.writerow(row)
                    f.flush()
                
                time.sleep(RATE_LIMIT_SECONDS)  # Rate limiting between pages
    print(f"Done. Data  saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
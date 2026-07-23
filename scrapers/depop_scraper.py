"""
Depop listings scraper for vintage heels pricing project.

PURPOSE:
    1. Search Depop for listings that match a query (e.g. "vintage heels").
    2. For each listing found/visited, pull out:
        - price
        - item specifics (e.g. size, color, brand, condition)
        - title + description text (to catch untagged information, such as condition details)
        - main image URL (and optionally, download the image)
    3. Save everything to a CSV file in data/raw/

HOW TO RUN:
    pip install requests beautifulsoup4 pandas
    python depop_scraper.py

"""

import time
import csv
import os
import re
from urllib.parse import urlencode
import pathlib
from bs4 import BeautifulSoup
import requests

from scrapers.ebay_scraper import HEADERS

# -----------------------------------------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------------------------------------

SEARCH_TERMS = [
    "vintage heels",
    "vintage kitten heels",
    "vintage stilettos",
    "vintage boots",
    "vintage sandals",
]

RATE_LIMIT_SECONDS = 3.0
DOWNLOAD_IMAGES = True
SCRIPT_DIR = pathlib.Path(__file__).parent
DEPOP_OUTPUT_CSV = SCRIPT_DIR / "../data/raw/heels_listings.csv"
DEPOP_IMAGE_DIR = SCRIPT_DIR / "../data/images"

# -----------------------------------------------------------------------------------------------------------
# SEARCH RESULTS PAGE
# -----------------------------------------------------------------------------------------------------------

def build_search_url(query: str, after:  str | None = None) -> str:
    """ 
    Builds a Depop search URL for a given query. 
    If "after" is provided, includes it to fetch the next batch of results.
    """
    params = {
        "what": query,
        "limit": 24,
        "country": "us",
        "currency": "USD",
    }

    if after is not None:
        params["after"] = after

    return "https://www.depop.com/presentation/api/v1/search/products/?" + urlencode(params)

def get_all_listings(query: str) -> list[dict]:
    """
    Given a search query, returns a list of urls for all listings found on Depop.
    """

    all_listings = []
    after = None  # No cursor yet on the first request

    while True:
        search_url = build_search_url(query, after)
        resp = requests.get(search_url, headers=HEADERS)
        data = resp.json()

        for listing in data["objects"]:
            id = listing["id"]
            brand_id = listing["brand_id"]
            brand_name = listing["brand_name"]
            description = listing["description"]
            condition = listing["condition"]
            total_price = parse_price(listing["pricing"]["current_price"]["total_price"])
            image_url = listing["pictures"][0]["formats"]["P0"]["url"]
            shoe_type = listing["shoe_type"] if "shoe_type" in listing else None

            all_listings.append({
                "id": id,
                "brand_id": brand_id,
                "brand_name": brand_name,
                "description": description,
                "condition": condition,
                "total_price": total_price,
                "image_url": image_url,
                "shoe_type": shoe_type,
            })

        time.sleep(RATE_LIMIT_SECONDS)
        
        if not data["page_info"]["has_more"]:
            break
        after = data["page_info"]["last"]

    return all_listings

def parse_price (total_price: str) -> float | None:
    """Retrieve the current price and convert it into a float."""
    try:
        return float(total_price)
    except (ValueError, TypeError):
        return None

def download_image(image_url: str, id: str) -> str | None:
    """
    Downloads the image from image_url and saves it to DEPOP_IMAGE_DIR with a filename
    based on the id. Returns the local file path if successful or None if failed.
    """
    if not image_url:
        return None
    os.makedirs(DEPOP_IMAGE_DIR, exist_ok=True)
    ext = ".jpg"
    image_local_path = os.path.join(DEPOP_IMAGE_DIR, f"{id}{ext}")
    try:
        resp = requests.get(image_url, timeout=15)
        resp.raise_for_status()
        with open(image_local_path, "wb") as f:
            f.write(resp.content)
        return image_local_path
    except requests.RequestException:
        return None

# -----------------------------------------------------------------------------------------------------------
# MAIN FUNCTION
# -----------------------------------------------------------------------------------------------------------

def main():
    os.makedirs(os.path.dirname(DEPOP_OUTPUT_CSV), exist_ok=True)
    write_header = not os.path.exists(DEPOP_OUTPUT_CSV)

    with open(DEPOP_OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "id",
            "brand_id",
            "brand_name",
            "description",
            "condition",
            "total_price",
            "image_url",
            "shoe_type",
            "image_local_path",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        seen_ids = set()

        for query in SEARCH_TERMS:
            print(f"Searching Depop for '{query}'...")
            listings = get_all_listings(query)

            for listing in listings:
                if listing["id"] in seen_ids:
                    continue
                seen_ids.add(listing["id"])

                image_local_path = ""
                if DOWNLOAD_IMAGES and listing.get("image_url"):
                    downloaded = download_image(listing["image_url"], listing["id"])
                    image_local_path = downloaded or ""

                row = {
                    "id": listing["id"],
                    "brand_id": listing["brand_id"],
                    "brand_name": listing["brand_name"],
                    "description": listing["description"],
                    "condition": listing["condition"],
                    "total_price": listing["total_price"],
                    "image_url": listing["image_url"],
                    "shoe_type": listing["shoe_type"],
                    "image_local_path": image_local_path,
                }

                writer.writerow(row)
                f.flush()

        print(f"Done. Data saved to {DEPOP_OUTPUT_CSV}")

if __name__ == "__main__":
    main()
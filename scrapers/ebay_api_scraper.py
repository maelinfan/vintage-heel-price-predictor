"""
eBay sold-listings scraper with API integration for vintage heels pricing project.

PURPOSE:
1. Search eBay for sold listings that match a query (e.g. "vintage heels")
2. For each listing found/visited, pull out:
    - price
    - item specifics table (brand, style, heel height, material, color, size, condition, misc. details)
    - title + description text (to catch untagged fields such as 'era')
    - main image URL (and optionally download the image)
3. Save everything to a CSV file in data/raw/

HOW TO RUN:
    pip install requests beautifulsoup4 pandas
    python ebay_api_scraper.py
"""

import os
import time
import csv
import pathlib
import base64 
import requests
from dotenv import load_dotenv
import json

load_dotenv()

# -----------------------------------------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------------------------------------

SEARCH_TERMS = [
    "vintage heels",
    ###"vintage kitten heels",
    ###"vintage stilettos",
    ###"vintage boots",
    ###"vintage sandals",
]

RATE_LIMIT_SECONDS = 3.0
DOWNLOAD_IMAGES = True
SCRIPT_DIR = pathlib.Path(__file__).parent
EBAY_API_OUTPUT_CSV = SCRIPT_DIR / "../data/raw/heels_listings.csv"
EBAY_API_IMAGE_DIR = SCRIPT_DIR / "../data/images"

# -----------------------------------------------------------------------------------------------------------
# API CONFIG
# -----------------------------------------------------------------------------------------------------------

CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")

def get_access_token() -> str:
    """
    Generates and returns an access_token using eBay's API access.
    """
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
    }
    body = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }

    resp = requests.post(url=url, headers=headers, data=body)
    token = resp.json()
    access_token = token["access_token"]
    return access_token


# -----------------------------------------------------------------------------------------------------------
# SEARCH RESULTS PAGE
# -----------------------------------------------------------------------------------------------------------

def search_items(query: str, access_token: str, offset: int) -> dict:
    """
    Builds an eBay search URL for a given query.
    """
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }
    params = {
        "q": query,
        "limit": 50,
        "offset": offset
    }

    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()
    return data

def get_all_items(query: str, access_token: str) -> list[dict]:
    """
    Given a search query, returns all of the listings for that query.
    """
    all_listings = []
    offset = 0

    while len(all_listings) <= 100:
        listing = search_items(query, access_token, offset)

        for item in listing["itemSummaries"]:
            itemId = item["itemId"]
            title = item["title"]
            specificCategory = item["categories"][0]["categoryName"]
            price = item["price"]["value"]
            itemURL = item["itemHref"]
            condition = item["condition"]
            imageURL = item["thumbnailImages"][0]["imageUrl"]

            all_listings.append({
                "itemId": itemId,
                "title": title,
                "specificCategory": specificCategory,
                "price": price,
                "itemURL": itemURL,
                "condition": condition,
                "imageURL": imageURL,
            })

        time.sleep(RATE_LIMIT_SECONDS)

        if offset < listing["total"]:
            offset = listing["limit"] + offset
        else:
            break

    return all_listings

def parse_price(price: str) -> float | None:
    """
    Converts the price into a float if necessary.
    """
    try:
        return float(price)
    except (ValueError, TypeError):
        return None

def download_image(imageURL: str, itemId: str) -> str | None:
    """
    Downloads the image from imageURL and saves it to EBAY_API_IMAGE_DIR with a filename
    based on the itemId. Returns the local file path if successful or None if failed.
    """
    if not imageURL:
        return None
    os.makedirs(EBAY_API_IMAGE_DIR, exist_ok=True)

    safe_id = itemId.replace("|", "_").replace("/", "_")

    ext = ".jpg"
    image_local_path = os.path.join(EBAY_API_IMAGE_DIR, f"{safe_id}{ext}")
    try:
        resp = requests.get(imageURL, timeout=15)
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
    os.makedirs(os.path.dirname(EBAY_API_OUTPUT_CSV), exist_ok=True)
    write_header = not os.path.exists(EBAY_API_OUTPUT_CSV)

    with open(EBAY_API_OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "itemId",
            "title",
            "specificCategory",
            "price",
            "itemURL",
            "condition",
            "imageURL",
            "image_local_path",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        access_token = get_access_token()
        seen_ids = set()
        

        for query in SEARCH_TERMS:
            print(f"Searching eBay for '{query}'...")
            data = get_all_items(query, access_token)

            for listing in data:
                if listing["itemId"] in seen_ids:
                    continue
                seen_ids.add(listing["itemId"])

                image_local_path = ""
                if DOWNLOAD_IMAGES and listing.get("imageURL"):
                    downloaded = download_image(listing["imageURL"], listing["itemId"])
                    image_local_path = downloaded or ""

                row = {
                    "itemId": listing["itemId"],
                    "title": listing["title"],
                    "specificCategory": listing["specificCategory"],
                    "price": listing["price"],
                    "itemURL": listing["itemURL"],
                    "condition": listing["condition"],
                    "imageURL": listing["imageURL"],
                    "image_local_path": image_local_path,
                }

                writer.writerow(row)
                f.flush()

        print(f"Done. Data saved to {EBAY_API_OUTPUT_CSV}")

if __name__ == "__main__":
    main()

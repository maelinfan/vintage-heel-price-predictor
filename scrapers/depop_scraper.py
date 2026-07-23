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
        if not data["page_info"]["has_more"]:
            break
        after = data["page_info"]["last"]

    return all_listings

def parse_price (total_price: str) -> float | None:
    # Retrieve the current price and convert it into a float
    try:
        return float(total_price)
    except (ValueError, TypeError):
        return None
    
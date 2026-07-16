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
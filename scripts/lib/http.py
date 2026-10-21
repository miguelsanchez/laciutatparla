"""Shared HTTP utilities for the pipeline scripts."""

import random
import time

import requests
from bs4 import BeautifulSoup


def fetch_with_retry(
    url: str,
    retries: int = 4,
    timeout: int = 30,
    stream: bool = False,
) -> requests.Response:
    """GET with exponential backoff + jitter. Raises on final failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout, stream=stream)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"  [retry {attempt + 1}/{retries - 1}, {wait:.1f}s — {e}]", flush=True)
            time.sleep(wait)


def fetch_html(url: str, retries: int = 4, timeout: int = 30) -> BeautifulSoup:
    """Fetch a URL and return parsed HTML."""
    resp = fetch_with_retry(url, retries=retries, timeout=timeout)
    return BeautifulSoup(resp.text, "html.parser")


def api_backoff(attempt: int) -> float:
    """Exponential backoff with jitter for API rate limits. Returns wait seconds."""
    wait = (2 ** attempt) * 5 + random.uniform(0, 2)
    return wait

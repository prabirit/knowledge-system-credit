"""Source authority: how much a page is trusted when pages disagree (lower rank wins)."""
from __future__ import annotations

import re
from urllib.parse import urlparse


def normal_url(url: str) -> str:
    """Lower-case host (without www) plus path, for comparing URLs."""
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/").lower())



def page_rank(url: str, title: str, text: str) -> int:
    """Authority rank of a page: 1 official rate sheet ... 7 files, 99 expired. Lower wins."""
    path = urlparse(url).path.lower().rstrip("/")
    lower_title = title.lower()
    if ("offer has expired" in lower_title or "offer has expired" in text[:500].lower()
            or re.search(r"offer ended\s+\d{4}-\d{2}-\d{2}", text, re.I)):
        return 99
    if path in ("/rates", "/business-rates") or path.startswith(("/rates/", "/business-rates/")):
        return 1
    if "/calculators" in path or "calculator" in path:
        return 4
    if path.startswith(("/learn/", "/business/resources/")):
        return 5
    if path.startswith("/newsroom/") or re.match(r"^/20\d{2}/", path):
        return 6
    if path.startswith("/hubfs/"):
        return 7
    if path.endswith("-lp") or path == "/switch-and-earn" or "offer" in path:
        return 3
    if path.startswith(("/personal/", "/business/", "/about/", "/contact")):
        return 2
    return 5

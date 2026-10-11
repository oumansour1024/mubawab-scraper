import re

def extract_price(text: str | None) -> int | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None

def extract_number(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None

def extract_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"/a/(\d+)/", url)
    return m.group(1) if m else None

from dataclasses import dataclass


@dataclass
class PaginationInfo:
    slug: str
    current_page: int
    last_page: int
    total_elements: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return self.last_page

    @property
    def has_next(self) -> bool:
        return self.current_page < self.last_page


def parse_pagination(soup, slug: str) -> PaginationInfo | None:
    """Extrait les métadonnées de pagination depuis le bloc #ads."""

    def _val(elem_id: str) -> str | None:
        el = soup.select_one(f"input#{elem_id}")
        return el.get("value") if el else None

    def _to_int(v: str | None, default: int = 0) -> int:
        try:
            return int(v) if v else default
        except (TypeError, ValueError):
            return default

    current_page = _to_int(_val("currentPage"), 1)
    total_elements = _to_int(_val("totalElements"), 0)
    page_size = _to_int(_val("pageSize"), 0)
    span = soup.select_one("span#lastPageSpan")
    last_page = _to_int(span.get_text(strip=True), 0) if span else 0
    if last_page == 0 and total_elements and page_size:
        last_page = (total_elements + page_size - 1) // page_size
    if last_page == 0 and total_elements:
        last_page = 1

    if total_elements <= 0:
        return None

    return PaginationInfo(
        slug=slug,
        current_page=current_page,
        last_page=last_page,
        total_elements=total_elements,
        page_size=page_size,
    )

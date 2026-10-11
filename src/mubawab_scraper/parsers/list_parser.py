"""Extract city listing URLs and names from Mubawab HTML."""

from html.parser import HTMLParser
import re
from typing import TypedDict


class CityLink(TypedDict):
	url: str
	city: str


class _CityLinkHTMLParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.links: list[CityLink] = []
		self._href: str | None = None
		self._text: list[str] = []

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag.lower() != "a":
			return
		href = dict(attrs).get("href")
		if href and "/ct/" in href:
			self._href = href.strip()
			self._text = []

	def handle_data(self, data: str) -> None:
		if self._href is not None:
			self._text.append(data)

	def handle_endtag(self, tag: str) -> None:
		if tag.lower() != "a" or self._href is None:
			return

		label = re.sub(r"\s+", " ", " ".join(self._text)).strip()
		city = re.sub(r"^Immobilier\s+", "", label, flags=re.IGNORECASE).strip()
		if city:
			self.links.append({"url": self._href, "city": city})
		self._href = None
		self._text = []


def parse_city_links(html: str) -> list[CityLink]:
	"""Return ``url`` and ``city`` for each city listing link in ``html``."""
	parser = _CityLinkHTMLParser()
	parser.feed(html)
	return parser.links

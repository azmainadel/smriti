"""Product pages: structured data first (JSON-LD, then OpenGraph product tags)."""

from typing import Any

from smriti.models import ItemType
from smriti.pipeline.extractors import html as h
from smriti.pipeline.extractors.base import Extraction


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _image(value: Any) -> str | None:
    value = _first(value)
    if isinstance(value, dict):
        return value.get("url") or value.get("contentUrl")
    return value if isinstance(value, str) else None


def _offer(offers: Any) -> dict[str, Any]:
    offer = _first(offers) or {}
    if not isinstance(offer, dict):
        return {}
    if "price" not in offer and "lowPrice" in offer:
        offer = {**offer, "price": offer["lowPrice"]}
    if "price" not in offer and isinstance(offer.get("priceSpecification"), dict):
        offer = {**offer, **offer["priceSpecification"]}
    return offer


def product_from_tree(tree: Any, tags: dict[str, str], url: str) -> Extraction | None:
    node = next((n for n in h.json_ld(tree) if "product" in h.ld_type(n)), None)
    price = currency = None
    if node:
        offer = _offer(node.get("offers"))
        price, currency = offer.get("price"), offer.get("priceCurrency")
        brand = _first(node.get("brand"))
        name = node.get("name")
        description = node.get("description")
        image = _image(node.get("image"))
        brand_name = brand.get("name") if isinstance(brand, dict) else brand
    elif tags.get("og:type", "").startswith("product") or "product:price:amount" in tags:
        price = tags.get("product:price:amount") or tags.get("og:price:amount")
        currency = tags.get("product:price:currency") or tags.get("og:price:currency")
        name, description = tags.get("og:title"), tags.get("og:description")
        image, brand_name = tags.get("og:image"), tags.get("product:brand")
    else:
        return None

    if not name:
        return None
    text = "\n\n".join(x for x in (name, brand_name, description) if x)
    return Extraction(
        title=str(name),
        text=text,
        html=h.text_to_html(text),
        site_name=tags.get("og:site_name"),
        description=description,
        canonical_url=h.canonical_link(tree, url),
        type=ItemType.product,
        image_urls=[image] if image else [],
        meta={
            k: v
            for k, v in {
                "price": str(price) if price is not None else None,
                "currency": currency,
                "brand": brand_name,
            }.items()
            if v
        },
    )

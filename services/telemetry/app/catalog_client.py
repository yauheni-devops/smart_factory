"""Запросы к catalog: есть ли такая площадка и не в резерве ли она."""

import os

import httpx

CATALOG_URL = os.environ.get("CATALOG_URL", "http://127.0.0.1:8081")


class CatalogError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_site(site_id: str) -> dict:
    url = f"{CATALOG_URL.rstrip('/')}/sites/{site_id}"
    try:
        response = httpx.get(url, timeout=2.0)
    except httpx.RequestError as exc:
        raise CatalogError(
            f"catalog недоступен ({CATALOG_URL}): {exc}",
            503,
        ) from exc

    if response.status_code == 404:
        raise CatalogError(f"Нет площадки {site_id}", 404)
    if response.status_code >= 400:
        raise CatalogError(f"catalog ответил {response.status_code}", 502)

    return response.json()


def list_sites() -> list[dict]:
    url = f"{CATALOG_URL.rstrip('/')}/sites"
    try:
        response = httpx.get(url, timeout=2.0)
    except httpx.RequestError as exc:
        raise CatalogError(
            f"catalog недоступен ({CATALOG_URL}): {exc}",
            503,
        ) from exc
    if response.status_code >= 400:
        raise CatalogError(f"catalog ответил {response.status_code}", 502)
    return response.json().get("items") or []

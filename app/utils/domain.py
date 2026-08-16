"""Domain normalization helpers."""

from __future__ import annotations


def normalize_domain(value: str) -> str:
    """Strip scheme, path, port, and leading www. Return lowercase host."""
    domain = value.strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix) :]
    domain = domain.split("/")[0]
    domain = domain.split("?")[0]
    domain = domain.split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    domain = domain.strip(".")
    if not domain:
        raise ValueError("domain must not be empty")
    return domain


def domains_match(left: str, right: str) -> bool:
    try:
        return normalize_domain(left) == normalize_domain(right)
    except ValueError:
        return False

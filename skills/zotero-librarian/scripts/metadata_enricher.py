#!/usr/bin/env python3
"""Build a safe zot apply JSONL plan from authoritative metadata sources."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ARXIV_ID = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.I)
ACL_ID = re.compile(r"aclanthology\.org/([^/?#]+)", re.I)
PMLR_URL = re.compile(r"https?://proceedings\.mlr\.press/[^\s]+\.html", re.I)
DOI_IN_URL = re.compile(r"(?:doi\.org/|/doi/(?:abs/|full/)?)(10\.\d{4,9}/[^?#]+)", re.I)
DOI_VALUE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
HTML_META = re.compile(
    r"<meta\s+[^>]*?(?:name|property)=[\"']([^\"']+)[\"'][^>]*?content=[\"']([^\"']*)[\"'][^>]*?>",
    re.I,
)
HTML_META_REVERSED = re.compile(
    r"<meta\s+[^>]*?content=[\"']([^\"']*)[\"'][^>]*?(?:name|property)=[\"']([^\"']+)[\"'][^>]*?>",
    re.I,
)
ACL_ABSTRACT = re.compile(
    r'<div[^>]*class=["\'][^"\']*acl-abstract[^"\']*["\'][^>]*>.*?<span>(.*?)</span>',
    re.I | re.S,
)
PMLR_ABSTRACT = re.compile(
    r'<div[^>]*id=["\']abstract["\'][^>]*>(.*?)</div>',
    re.I | re.S,
)
USER_AGENT = "zotero-librarian/1.0 (metadata enrichment; https://github.com/HY-LiYihan/zotero-librarian)"


class EnrichmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Metadata:
    title: str
    abstract: str
    source: str


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value)).casefold()
    value = value.replace("&", " and ")
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def titles_match(left: str, right: str) -> bool:
    a, b = normalize_title(left), normalize_title(right)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 40 and (a in b or b in a))


def clean_abstract(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", html.unescape(value))
    value = re.sub(r"^\s*(?:abstract\s*[:.—-]?\s*)", "", value, flags=re.I)
    return " ".join(value.split())


def request_text(url: str, *, accept: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")


def arxiv_identifier(item: dict[str, Any]) -> str | None:
    url = str(item.get("url") or "")
    match = ARXIV_ID.search(url)
    if match:
        return match.group(1).removesuffix(".pdf")
    doi = str(item.get("doi") or "")
    prefix = "10.48550/arxiv."
    if doi.casefold().startswith(prefix):
        return doi[len(prefix) :]
    return None


def deterministic_doi(item: dict[str, Any]) -> tuple[str, str] | None:
    if str(item.get("doi") or item.get("DOI") or "").strip():
        return None
    url = str(item.get("url") or "").strip()
    match = DOI_IN_URL.search(url)
    if match:
        doi = urllib.parse.unquote(match.group(1)).rstrip("/.,;)")
        return (doi, "URL") if DOI_VALUE.fullmatch(doi) else None
    identifier = arxiv_identifier(item)
    if identifier:
        identifier = re.sub(r"v\d+$", "", identifier, flags=re.I)
        return f"10.48550/arXiv.{identifier}", "arXiv"
    return None


def fetch_arxiv(item: dict[str, Any], timeout: float) -> Metadata | None:
    identifier = arxiv_identifier(item)
    if not identifier:
        return None
    url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(identifier)
    root = ET.fromstring(request_text(url, accept="application/atom+xml", timeout=timeout))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return None
    title = " ".join((entry.findtext("atom:title", default="", namespaces=ns)).split())
    abstract = clean_abstract(entry.findtext("atom:summary", default="", namespaces=ns))
    return Metadata(title, abstract, "arXiv") if title and abstract else None


def fetch_crossref(item: dict[str, Any], timeout: float) -> Metadata | None:
    doi = str(item.get("doi") or item.get("DOI") or "").strip()
    if not doi:
        match = DOI_IN_URL.search(str(item.get("url") or ""))
        doi = urllib.parse.unquote(match.group(1)).rstrip("/") if match else ""
    if not doi or doi.casefold().startswith("10.48550/arxiv."):
        return None
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    payload = json.loads(request_text(url, accept="application/json", timeout=timeout))
    message = payload.get("message", {})
    titles = message.get("title", [])
    title = str(titles[0]) if isinstance(titles, list) and titles else ""
    abstract = clean_abstract(str(message.get("abstract") or ""))
    return Metadata(title, abstract, "Crossref") if title and abstract else None


def openalex_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        positioned.extend((position, word) for position in positions if isinstance(position, int))
    return clean_abstract(" ".join(word for _, word in sorted(positioned)))


def fetch_openalex(item: dict[str, Any], timeout: float) -> Metadata | None:
    title = str(item.get("title") or "").strip()
    normalized = normalize_title(title)
    # Short generic titles produce unsafe exact-title collisions.
    if len(normalized) < 32 or len(normalized.split()) < 5:
        return None
    query = urllib.parse.urlencode({"search": title, "per-page": 5})
    payload = json.loads(
        request_text("https://api.openalex.org/works?" + query, accept="application/json", timeout=timeout)
    )
    expected_year = str(item.get("year") or "").strip()
    expected_doi = str(item.get("doi") or item.get("DOI") or "").strip().casefold()
    acl_match = ACL_ID.search(str(item.get("url") or ""))
    expected_acl_id = acl_match.group(1).casefold() if acl_match else ""
    candidates: list[Metadata] = []
    for work in payload.get("results", []):
        if not isinstance(work, dict):
            continue
        candidate_title = str(work.get("display_name") or work.get("title") or "")
        candidate_year = str(work.get("publication_year") or "")
        if not titles_match(title, candidate_title):
            continue
        if expected_year and candidate_year and expected_year != candidate_year:
            continue
        candidate_doi = str(work.get("doi") or "").removeprefix("https://doi.org/").casefold()
        locations = work.get("locations") if isinstance(work.get("locations"), list) else []
        location_urls = " ".join(
            str(location.get(field) or "").casefold()
            for location in locations
            if isinstance(location, dict)
            for field in ("landing_page_url", "pdf_url")
        )
        if expected_doi and candidate_doi != expected_doi:
            continue
        if expected_acl_id and expected_acl_id not in candidate_doi and expected_acl_id not in location_urls:
            continue
        abstract = openalex_abstract(work.get("abstract_inverted_index"))
        if abstract:
            candidates.append(Metadata(candidate_title, abstract, "OpenAlex"))
    return candidates[0] if len(candidates) == 1 else None


def html_metadata(text: str) -> dict[str, str]:
    values = {name.casefold(): html.unescape(value) for name, value in HTML_META.findall(text)}
    values.update({name.casefold(): html.unescape(value) for value, name in HTML_META_REVERSED.findall(text)})
    return values


def fetch_html_meta(item: dict[str, Any], timeout: float) -> Metadata | None:
    url = str(item.get("url") or "")
    acl = ACL_ID.search(url)
    source = "ACL Anthology" if acl else "PMLR" if PMLR_URL.fullmatch(url) else ""
    if not source:
        return None
    page = request_text(url, accept="text/html", timeout=timeout)
    metadata = html_metadata(page)
    title = metadata.get("citation_title") or metadata.get("og:title") or ""
    pattern = ACL_ABSTRACT if source == "ACL Anthology" else PMLR_ABSTRACT
    match = pattern.search(page)
    abstract = metadata.get("citation_abstract") or (match.group(1) if match else "")
    abstract = clean_abstract(abstract)
    return Metadata(title, abstract, source) if title and abstract else None


def fetch_official_description(item: dict[str, Any], timeout: float) -> Metadata | None:
    if str(item.get("type") or item.get("itemType") or "") != "document":
        return None
    url = str(item.get("url") or "")
    if not url.startswith(("https://", "http://")):
        return None
    page = request_text(url, accept="text/html", timeout=timeout)
    metadata = html_metadata(page)
    title = metadata.get("og:title") or metadata.get("twitter:title") or ""
    description = metadata.get("description") or metadata.get("og:description") or ""
    description = clean_abstract(description)
    if not title or not description or len(description) < 40:
        return None
    return Metadata(title, description, "official page")


PROVIDERS: tuple[Callable[[dict[str, Any], float], Metadata | None], ...] = (
    fetch_arxiv,
    fetch_html_meta,
    fetch_crossref,
    fetch_official_description,
    fetch_openalex,
)


def load_items(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EnrichmentError(f"cannot read input JSON: {exc}") from exc
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise EnrichmentError("input must be an item array or an object containing an items array")
    return items


def build_plan(
    items: list[dict[str, Any]], *, timeout: float, delay: float
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    plan: list[dict[str, Any]] = []
    report: list[dict[str, str]] = []
    for item in items:
        key, title = str(item.get("key") or ""), str(item.get("title") or "")
        if item.get("abstractNote"):
            report.append({"key": key, "status": "skipped", "reason": "abstract already present"})
            continue
        metadata = None
        last_error = "no supported authoritative source"
        for provider in PROVIDERS:
            try:
                metadata = provider(item, timeout)
            except (EnrichmentError, ET.ParseError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
                last_error = f"{provider.__name__}: {exc}"
                continue
            if metadata:
                break
        if not metadata:
            report.append({"key": key, "status": "unresolved", "reason": last_error})
            continue
        if not titles_match(title, metadata.title):
            report.append({"key": key, "status": "rejected", "reason": f"title mismatch from {metadata.source}"})
            continue
        plan.append({"key": key, "set": {"abstractNote": metadata.abstract}})
        report.append({"key": key, "status": "planned", "source": metadata.source})
        if delay:
            time.sleep(delay)
    return plan, report


def search_crossref_doi(item: dict[str, Any], timeout: float) -> str | None:
    item_type = str(item.get("type") or item.get("itemType") or "")
    if item_type not in {"bookSection", "conferencePaper", "journalArticle", "preprint"}:
        return None
    title = str(item.get("title") or "").strip()
    if len(normalize_title(title)) < 32:
        return None
    query = urllib.parse.urlencode({"query.title": title, "rows": 5, "select": "DOI,title,published"})
    payload = json.loads(
        request_text("https://api.crossref.org/works?" + query, accept="application/json", timeout=timeout)
    )
    expected_year = str(item.get("year") or "").strip()
    matches: set[str] = set()
    for work in payload.get("message", {}).get("items", []):
        if not isinstance(work, dict):
            continue
        titles = work.get("title")
        candidate_title = str(titles[0]) if isinstance(titles, list) and titles else ""
        date_parts = work.get("published", {}).get("date-parts", [])
        candidate_year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
        doi = str(work.get("DOI") or "").strip()
        if titles_match(title, candidate_title) and doi:
            if expected_year and candidate_year and expected_year != candidate_year:
                continue
            matches.add(doi)
    return next(iter(matches)) if len(matches) == 1 else None


def build_doi_plan(
    items: list[dict[str, Any]], *, search: bool = False, timeout: float = 20.0, delay: float = 0.0
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    plan: list[dict[str, Any]] = []
    report: list[dict[str, str]] = []
    for item in items:
        key = str(item.get("key") or "")
        result = deterministic_doi(item)
        if not result and search:
            try:
                searched_doi = search_crossref_doi(item, timeout)
            except (json.JSONDecodeError, urllib.error.URLError, TimeoutError):
                searched_doi = None
            if searched_doi:
                result = searched_doi, "Crossref exact title/year"
                if delay:
                    time.sleep(delay)
        if not result:
            reason = "DOI already present" if item.get("doi") or item.get("DOI") else "no deterministic DOI"
            report.append({"key": key, "status": "skipped", "reason": reason})
            continue
        doi, source = result
        plan.append({"key": key, "set": {"DOI": doi}})
        report.append({"key": key, "status": "planned", "source": source, "doi": doi})
    return plan, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON from a supported 'zot missing ... --json' command")
    parser.add_argument("--field", choices=("abstract", "doi"), default="abstract")
    parser.add_argument(
        "--search-doi",
        action="store_true",
        help="for DOI mode, query Crossref and require a unique exact title/year match",
    )
    parser.add_argument("--output", type=Path, help="write JSONL plan here; defaults to stdout")
    parser.add_argument("--report", type=Path, help="write a JSON audit report here")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--delay", type=float, default=0.1, help="delay between successful requests")
    args = parser.parse_args()
    try:
        items = load_items(args.input)
        if args.field == "doi":
            plan, report = build_doi_plan(
                items, search=args.search_doi, timeout=args.timeout, delay=args.delay
            )
        else:
            plan, report = build_plan(items, timeout=args.timeout, delay=args.delay)
    except EnrichmentError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in plan)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"planned={len(plan)} unresolved={len(report) - len(plan)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

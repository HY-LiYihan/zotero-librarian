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


PROVIDERS: tuple[Callable[[dict[str, Any], float], Metadata | None], ...] = (
    fetch_arxiv,
    fetch_html_meta,
    fetch_crossref,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON from 'zot missing abstract --json'")
    parser.add_argument("--output", type=Path, help="write JSONL plan here; defaults to stdout")
    parser.add_argument("--report", type=Path, help="write a JSON audit report here")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--delay", type=float, default=0.1, help="delay between successful requests")
    args = parser.parse_args()
    try:
        plan, report = build_plan(load_items(args.input), timeout=args.timeout, delay=args.delay)
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

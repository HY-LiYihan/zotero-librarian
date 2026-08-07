#!/usr/bin/env python3
"""Audit whether item URLs/DOIs resolve to the same bibliographic identity."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .metadata_enricher import (
    ACL_ID,
    ARXIV_ID,
    DOI_IN_URL,
    PMLR_URL,
    clean_abstract,
    html_metadata,
    normalize_title,
    request_text,
    titles_match,
)


CHILD_TYPES = {"annotation", "attachment", "note"}


class IdentityAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class IdentityRecord:
    title: str
    source: str
    evidence: dict[str, str] = field(default_factory=dict)


def load_items(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityAuditError(f"cannot read input JSON: {exc}") from exc
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise IdentityAuditError("input must be an item array or an object containing an items array")
    return items


def item_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def item_key(item: dict[str, Any]) -> str:
    data = item_data(item)
    return str(item.get("key") or data.get("key") or "")


def fetch_html_record(item: dict[str, Any], timeout: float) -> IdentityRecord | None:
    url = str(item.get("url") or "").strip()
    acl = ACL_ID.search(url)
    source = "ACL Anthology" if acl else "PMLR" if PMLR_URL.fullmatch(url) else ""
    if not source:
        return None
    page = request_text(url, accept="text/html", timeout=timeout)
    metadata = html_metadata(page)
    title = metadata.get("citation_title") or metadata.get("og:title") or ""
    title = " ".join(title.split())
    if not title:
        return None
    evidence = {"url": url}
    if acl:
        evidence["aclId"] = acl.group(1)
    return IdentityRecord(title, source, evidence)


def crossref_record(doi: str, timeout: float, *, source: str = "Crossref") -> IdentityRecord | None:
    if not doi or doi.casefold().startswith("10.48550/arxiv."):
        return None
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    payload = json.loads(request_text(url, accept="application/json", timeout=timeout))
    message = payload.get("message", {})
    titles = message.get("title", [])
    title = clean_abstract(str(titles[0])) if isinstance(titles, list) and titles else ""
    return IdentityRecord(title, source, {"doi": doi}) if title else None


def fetch_crossref_url_record(item: dict[str, Any], timeout: float) -> IdentityRecord | None:
    match = DOI_IN_URL.search(str(item.get("url") or ""))
    doi = urllib.parse.unquote(match.group(1)).rstrip("/.,;)") if match else ""
    return crossref_record(doi, timeout, source="Crossref URL")


def fetch_crossref_doi_field_record(item: dict[str, Any], timeout: float) -> IdentityRecord | None:
    doi = str(item.get("doi") or item.get("DOI") or "").strip()
    return crossref_record(doi, timeout, source="Crossref DOI field")


def fetch_arxiv_record(item: dict[str, Any], timeout: float) -> IdentityRecord | None:
    url = str(item.get("url") or "")
    match = ARXIV_ID.search(url)
    identifier = match.group(1).removesuffix(".pdf") if match else ""
    doi = str(item.get("doi") or item.get("DOI") or "")
    prefix = "10.48550/arxiv."
    if not identifier and doi.casefold().startswith(prefix):
        identifier = doi[len(prefix) :]
    if not identifier:
        return None
    api_url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(identifier)
    root = ET.fromstring(request_text(api_url, accept="application/atom+xml", timeout=timeout))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return None
    title = " ".join(entry.findtext("atom:title", default="", namespaces=ns).split())
    return IdentityRecord(title, "arXiv", {"arxivId": identifier}) if title else None


URL_PROVIDERS: tuple[Callable[[dict[str, Any], float], IdentityRecord | None], ...] = (
    fetch_html_record,
    fetch_crossref_url_record,
    fetch_arxiv_record,
)
DOI_FIELD_PROVIDERS: tuple[Callable[[dict[str, Any], float], IdentityRecord | None], ...] = (
    fetch_crossref_doi_field_record,
)
PROVIDERS = URL_PROVIDERS


def audit_one(
    key: str,
    data: dict[str, Any],
    title: str,
    providers: tuple[Callable[[dict[str, Any], float], IdentityRecord | None], ...],
    timeout: float,
) -> dict[str, Any]:
    record = None
    last_error = "no supported URL or DOI identity source"
    for provider in providers:
        try:
            record = provider(data, timeout)
        except (ET.ParseError, json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{provider.__name__}: {exc}"
            continue
        if record:
            break
    if not record:
        return {"key": key, "status": "unresolved", "reason": last_error}
    status = "match" if titles_match(title, record.title) else "conflict"
    entry: dict[str, Any] = {
        "key": key,
        "status": status,
        "source": record.source,
        "zoteroTitle": title,
        "sourceTitle": record.title,
    }
    if record.evidence:
        entry["evidence"] = record.evidence
    if status == "conflict":
        entry["normalizedZoteroTitle"] = normalize_title(title)
        entry["normalizedSourceTitle"] = normalize_title(record.title)
    return entry


def audit_candidates(
    items: list[dict[str, Any]],
    *,
    keys: set[str] | None = None,
) -> list[tuple[str, dict[str, Any], str]]:
    candidates: list[tuple[str, dict[str, Any], str]] = []
    for item in items:
        data = item_data(item)
        key = item_key(item)
        if keys is not None and key not in keys:
            continue
        if data.get("itemType") in CHILD_TYPES:
            continue
        title = str(data.get("title") or "").strip()
        if not key or not title:
            continue
        candidates.append((key, data, title))
    return candidates


def audit_identity(
    items: list[dict[str, Any]],
    *,
    timeout: float,
    delay: float,
    include_doi_field: bool = False,
    keys: set[str] | None = None,
    workers: int = 1,
) -> list[dict[str, Any]]:
    providers = URL_PROVIDERS + (DOI_FIELD_PROVIDERS if include_doi_field else ())
    candidates = audit_candidates(items, keys=keys)
    if workers > 1:
        results: dict[int, dict[str, Any]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(audit_one, key, data, title, providers, timeout): index
                for index, (key, data, title) in enumerate(candidates)
            }
            for future in concurrent.futures.as_completed(futures):
                results[futures[future]] = future.result()
        return [results[index] for index in sorted(results)]

    report: list[dict[str, Any]] = []
    for key, data, title in candidates:
        report.append(audit_one(key, data, title, providers, timeout))
        if delay:
            time.sleep(delay)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON from 'zot search ... --all --json' or item array")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--delay", type=float, default=0.1, help="delay between successful requests")
    parser.add_argument("--output", type=Path, help="write JSON report here; defaults to stdout")
    parser.add_argument("--only-conflicts", action="store_true", help="omit matches and unresolved entries")
    parser.add_argument("--keys", help="comma-separated item keys to audit")
    parser.add_argument("--workers", type=int, default=1, help="parallel fetch workers; use modest values")
    parser.add_argument(
        "--include-doi-field",
        action="store_true",
        help="also query Crossref for DOI fields; slower on full libraries",
    )
    args = parser.parse_args()
    keys = set(args.keys.split(",")) if args.keys else None
    try:
        report = audit_identity(
            load_items(args.input),
            timeout=args.timeout,
            delay=args.delay,
            include_doi_field=args.include_doi_field,
            keys=keys,
            workers=max(1, args.workers),
        )
    except IdentityAuditError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 2
    output_report = [entry for entry in report if entry["status"] == "conflict"] if args.only_conflicts else report
    result = {
        "ok": True,
        "itemsChecked": len(report),
        "conflicts": sum(1 for entry in report if entry["status"] == "conflict"),
        "unresolved": sum(1 for entry in report if entry["status"] == "unresolved"),
        "report": output_report,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0 if result["conflicts"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

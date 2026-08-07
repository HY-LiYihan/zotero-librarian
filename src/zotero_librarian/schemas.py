from __future__ import annotations

from typing import Any


SCHEMAS: dict[str, dict[str, Any]] = {
    "plan": {
        "description": "One JSON object per line for reviewable Zotero changes.",
        "fields": {
            "key": "Required 8-character Zotero parent item key.",
            "set": "Object of simple Zotero fields to update; never include creators, tags, collections, relations, or itemType.",
            "setCreators": "Complete replacement creator list for authoritative metadata repairs.",
            "setItemType": "Target Zotero item type for guarded item-type repairs.",
            "addTags": "List of tags to add.",
            "removeTags": "List of tags to remove.",
            "addToCollection": "Collection name for upstream zot apply plans.",
            "trash": "Boolean; true moves the item to Zotero Trash only.",
        },
        "example": {
            "key": "ABCD1234",
            "set": {"abstractNote": "Verified abstract"},
            "addTags": ["topic:nlp"],
            "removeTags": ["status:needs-review"],
        },
    },
    "audit": {
        "description": "Whole-library parent-item completeness audit result.",
        "fields": {
            "parents": "Number of bibliographic parent items, excluding notes, annotations, and attachments.",
            "withPdf": "Parent items with a PDF attachment link.",
            "withoutPdf": "Parent items without a PDF attachment link.",
            "topicCoverage": "Parent items that have at least one topic:* tag.",
            "findings": "Lists of item keys by audit issue.",
            "counts": "Issue counts matching findings.",
            "errors": "Strict completion failures when --strict or --expect-items is used.",
        },
    },
    "status": {
        "description": "Completion gate summary for automation and full strict completion.",
        "fields": {
            "parentCount": "Current parent-item count.",
            "parentCountOk": "Whether the count matches --expect-items, if provided.",
            "automationComplete": "True when no actionable automated cleanup remains.",
            "fullComplete": "True when no review/conflict/manual decision remains.",
            "manualDecisionRequired": "True when a documented metadata conflict still needs a user identity choice.",
            "nextActions": "Recommended follow-up actions.",
        },
    },
}


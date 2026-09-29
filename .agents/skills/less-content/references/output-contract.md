# Less Brief output contract

Each item in `retention_ready` must be a JSON object accepted by `POST /api/briefs`:

```json
{
  "id": "stable-url-safe-id",
  "title": "准确、简短的标题",
  "published_at": "2026-09-22",
  "topics": ["Agents"],
  "important": true,
  "useful": false,
  "confidence": "high",
  "sources": [
    {
      "name": "来源名称",
      "url": "https://example.com/specific-page",
      "type": "official_docs",
      "primary": true,
      "published_at": "2026-09-22T09:00:00+08:00"
    }
  ],
  "what_happened": "主体及此前状态。此次具体新增、移除或改变了什么，以及有依据的结果。当前可用范围和影响理解的关键条件。",
  "why_it_matters": "为什么重要或有用、影响谁。",
  "our_take": null,
  "uncertainty": null
}
```

Rules:

- `id` starts with an ASCII letter or digit and then uses only letters, digits, `.`, `_`, `:`, or `-`.
- `published_at` accepts `YYYY-MM-DD`, a timezone-qualified ISO 8601 timestamp, or `null`. Never substitute the task date for an unknown publication date.
- `topics` contains 1–12 non-duplicated names grounded in retained content.
- At least one of `important` and `useful` is `true`.
- `confidence` is `high` or `medium`; low-confidence leads belong in `needs_verification`.
- `sources` contains 1–20 unique, concrete HTTP(S) page links. At least one source has `primary: true`.
- Source `type` is one of `official_docs`, `release`, `paper`, `blog`, `media`, or `other`.
- `what_happened` must stand on its own: give enough verified background, concrete change, current status, and material conditions for a reader to understand the event without opening the source. Use short paragraphs (`\n\n` in JSON) when helpful; do not replace substance with a one-line announcement or move interpretation into this field.
- Medium confidence requires a non-empty `uncertainty`. Known limitations must not be hidden behind `null`.
- `our_take` is `null` when no useful independent judgment exists.
- Each saveable Brief is plain JSON without placeholders or comments, so the management page can parse it directly.

## Time-bounded discovery batch

For a time-bounded scan, keep the saveable Briefs in `retention_ready` and wrap them with the process note below. Copy only `retention_ready` into the Less management page. The wrapper is for delivery and local checking, not a new stored Less object.

```json
{
  "retention_ready": [],
  "needs_verification": [],
  "task_note": {
    "window_start": "2026-09-26T10:00:00+08:00",
    "window_end": "2026-09-28T10:00:00+08:00",
    "timezone": "Asia/Shanghai",
    "time_basis": "first_primary_publication",
    "scan_scope": "broad",
    "coverage_considered": ["Frontier", "Builders", "Voices", "Signals"],
    "preferred_sources_checked": ["OpenAI News"],
    "expanded_sources_used": [],
    "access_limitations": [],
    "deduplication_basis": "Compared with retained Brief IDs and source links.",
    "no_item_qualified": true
  }
}
```

Use the actual timestamps and sources checked; the values above only illustrate the shape. `scan_scope` is `broad` or `focused`. For a broad scan, `preferred_sources_checked` cannot be empty. `needs_verification` contains readable strings, not saveable Brief objects. A first-primary-source date that is outside the exact window is excluded, even if a newer article discusses it. A date-only source on a partly covered boundary day remains unverified unless a reliable publication time is found. The authorized early/evening scheduler is the exception: it uses a 24-hour lookback and `--allow-date-only-overlap`, compares candidate Briefs with bounded matches from the full-library index, and never claims a precise 12-hour publication time for date-only sources. If the user explicitly asks for older events with new material changes, explain that different selection basis in the task note and assess the change manually rather than using the strict-window checker.

For manual delivery, run `.venv/bin/python .agents/skills/less-content/scripts/check_batch.py <draft.json> --existing-briefs <briefs.json>` before delivery, providing the complete unfiltered JSON array from the read-only `/api/briefs` endpoint. Use `--dedup-unavailable` only when retained Briefs cannot be obtained. The scheduled host instead performs an indexed historical comparison and runs this checker with `--host-checked`; the first discovery pass must not claim that comparison is already complete. The checker applies the same Brief field validation as the Less API and checks the declared window against the first primary source. Manual mode also detects exact ID/source-link duplicates in the provided retained Brief list. It does not verify that source pages were opened, that the stated publication time is true, or that the item is worth reading.

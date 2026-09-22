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
  "what_happened": "已核实的事实。",
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
- Medium confidence requires a non-empty `uncertainty`. Known limitations must not be hidden behind `null`.
- `our_take` is `null` when no useful independent judgment exists.
- Output plain JSON, without placeholders or comments, so the management page can parse it directly.

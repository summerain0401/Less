---
name: less-content
description: Find, verify, filter, and summarize AI-related information into structured Less Brief drafts. Use for Less content discovery, daily Brief preparation, source verification, or topic research; do not use for saving or publishing drafts.
---

# Less Content

Turn scattered information into a small set of trustworthy Brief drafts through Find → Filter → Verify → Summarize.

Before working, read the current project rules:

- [Less principles](../../../docs/current/00-less-principles.md)
- [Lite architecture](../../../docs/current/01-less-lite-architecture.md)
- [Content method](../../../docs/current/02-content-skill.md)

## Inputs

Use the time range, timezone, topics, reader need, available sources, and recent retained Briefs supplied by the task. If a non-critical input is missing, choose a reasonable narrow default and disclose it. Do not claim exhaustive coverage.

For rolling windows such as “past 48 hours,” record the exact start and end with timezone before searching. Unless the user asks for coverage of older events, use the first publication of the concrete primary source to decide whether an item is in range. A later report, repost, or page update does not reset that date. If a date-only source falls on a partial boundary day and its time cannot be established, put the lead in `needs_verification` instead of treating it as in range. The authorized early/evening digest uses a 24-hour lookback exception: a verified, date-only original source whose local date overlaps that lookback may be retained after full-library deduplication, without claiming a precise 12-hour publication time.

## Source strategy

When the task requires discovery, use the Coverage Map and Source Map in the [content method](../../../docs/current/02-content-skill.md), then read [the preferred source list](references/preferred-sources.md) before searching. Use this order:

1. Check sources explicitly required by the user.
2. Select a small, topic-relevant subset of the preferred sources.
3. Expand beyond the list when coverage is missing, an important claim needs independent verification, or a credible lead points to another original source.

The list is a search starting point, not an allowlist, a completeness promise, or a trust score. A preferred publisher's page still needs the same claim-level verification as any other source. For a broad daily scan, consider relevant Frontier, Builders, Voices, and cross-event Signals material across multiple organizations and source roles. Include intelligence or discovery routes when relevant. Do not visit every listed source merely to satisfy a quota.

Selected social accounts can reveal first-hand views, direct experience, or early product clues. Open the concrete post, verify its author, date, wording, and thread context, then follow any cited documentation or evidence. A person's own view can be primary for that view; a repost, teaser, or claimed product effect does not establish that the product shipped or the effect is real. Treat inaccessible posts as leads only, and deduplicate the same claim across posts, blogs, and announcements.

## Work

1. Find a small set of relevant leads, starting with original releases, documentation, papers, repositories, or first-hand accounts.
2. Keep an item only when it is Important or Useful for a specific audience. Merge repeated coverage and identify the actual increment over retained Briefs.
3. Open the concrete source pages and verify dates, availability, scope, conditions, and material claims. Distinguish publisher claims from independent confirmation.
4. Write clear Chinese Briefs that separate verified facts, reader value, Less judgment, and uncertainty. Make `what_happened` self-contained: explain the concrete change and the context, availability, and conditions needed to understand it, rather than compressing it into a one-line announcement. Follow the [content method](../../../docs/current/02-content-skill.md) for the writing standard.

Do not create collection queues, candidates, events, evidence records, scores, or review gates. Do not save drafts to Less or call its write API. A read-only Brief listing may be used for deduplication; if unavailable, disclose the limit. Saving requires a separate, explicit user decision in the product.

## Deliver

Read [the output contract](references/output-contract.md) before delivering. Return three clearly separated groups:

- `retention_ready`: only high- or medium-confidence Brief JSON objects that pass the contract.
- `needs_verification`: low-confidence leads as readable notes, never disguised as saveable Brief JSON.
- `task_note`: the actual search range, relevant Coverage considered, preferred sources checked, any expanded sources used, access limitations, deduplication basis, and whether no item qualified.

An empty `retention_ready` list is valid. Never invent a link, date, quote, result, or first-hand experience. Keep stable IDs unchanged when correcting an existing Brief.

For a time-bounded discovery task, prepare the [structured task note and batch](references/output-contract.md), then run `.venv/bin/python .agents/skills/less-content/scripts/check_batch.py <draft.json> --existing-briefs <briefs.json>` before delivery. Supply the complete, unfiltered read-only `/api/briefs` list for deduplication. If retained Briefs cannot be accessed, use `--dedup-unavailable` and state that limit in `task_note`. In the read-only scheduled digest, return the batch without writing files; the host scheduler runs this checker before any save. Resolve checker errors by correcting the source/date or moving the item to `needs_verification`; do not change dates to make an item pass. The checker validates stated dates, structure, and exact ID/source-link duplicates; it cannot prove pages were read or decide editorial value. Review those against the actual opened sources and tool results.

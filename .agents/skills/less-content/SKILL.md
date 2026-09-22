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

## Work

1. Find a small set of relevant leads, starting with original releases, documentation, papers, repositories, or first-hand accounts.
2. Keep an item only when it is Important or Useful for a specific audience. Merge repeated coverage and identify the actual increment over retained Briefs.
3. Open the concrete source pages and verify dates, availability, scope, conditions, and material claims. Distinguish publisher claims from independent confirmation.
4. Write concise Chinese Briefs that separate verified facts, reader value, Less judgment, and uncertainty.

Do not create collection queues, candidates, events, evidence records, scores, or review gates. Do not save drafts to Less or call its API. Saving requires a separate, explicit user decision in the product.

## Deliver

Read [the output contract](references/output-contract.md) before delivering. Return three clearly separated groups:

- `retention_ready`: only high- or medium-confidence Brief JSON objects that pass the contract.
- `needs_verification`: low-confidence leads as readable notes, never disguised as saveable Brief JSON.
- `task_note`: the actual search range, access limitations, deduplication basis, and whether no item qualified.

An empty `retention_ready` list is valid. Never invent a link, date, quote, result, or first-hand experience. Keep stable IDs unchanged when correcting an existing Brief.

# Less preferred sources

Use this list as the first search surface for discovery tasks. Select only entries relevant to the requested topic and time range. Sources outside the list remain allowed when they improve coverage or verification.

This list retains the concrete nodes from the original [Source Registry](../../../../operations/source-registry.json), while allowing later additions. Select entries across the original [Coverage Map and Source Map](../../../../docs/current/02-content-skill.md) as the task requires. `role` names a node's main editorial role; it does not determine the Brief source field `primary` and does not confer trust automatically:

- `primary`: an organization publishing its own releases, research, documentation, or repository changes.
- `people`: a person's first-hand thinking, experience, or long-form analysis within a specific area.
- `builders`: implementation notes, engineering practice, reproducible methods, and failure reports.
- `intelligence`: professional reporting, research, interviews, or independent evaluation that adds context or challenges claims.
- `discovery`: a lead surface; follow a lead to the concrete original page before using it in a Brief.

Do not add collection intervals, health status, authority scores, or selection metrics here. For a publisher claim about performance, impact, price, or comparative advantage, attribute the claim and seek independent support when it affects the conclusion.

## Official models, products, and research

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `openai-news` | [OpenAI News](https://openai.com/news/) | `primary` | Models, Agents, AI Coding, Products, Safety | First-party releases and research; company claims are not independent validation. |
| `anthropic-news` | [Anthropic Newsroom](https://www.anthropic.com/news) | `primary` | Models, Agents, Research, Safety | First-party Claude and Anthropic updates; distinguish availability from announced plans. |
| `deepmind-blog` | [Google DeepMind Blog](https://deepmind.google/discover/blog/) | `primary` | Models, Reasoning, Science, Safety | First-party research and product claims; open linked papers and technical reports. |
| `google-research` | [Google Research Blog](https://research.google/blog/) | `primary` | Research, Evaluation, Applications | Research-team summaries; use the linked paper for technical claims. |
| `meta-ai` | [Meta AI Blog](https://ai.meta.com/blog/) | `primary` | Open Source, Models, Research, Applications | First-party releases; verify license, weights, code, and availability separately. |
| `microsoft-research-ai` | [Microsoft Research AI](https://www.microsoft.com/en-us/research/research-area/artificial-intelligence/) | `primary` | Research, Agents, Engineering, Applications | Broad research index; prefer the concrete project, paper, or release page. |
| `mistral-news` | [Mistral News](https://mistral.ai/news/) | `primary` | Models, Open Source, Agents, Products | First-party announcements; verify model terms and actual access. |
| `xai-news` | [xAI News](https://x.ai/news) | `primary` | Models, APIs, Agents, Products | First-party announcements; performance comparisons require attribution or corroboration. |
| `deepseek-news` | [DeepSeek Research & News](https://deepseek.com/en/news/) | `primary` | Models, Reasoning, Open Source, APIs | First-party releases; open technical reports, model cards, and repositories when available. |
| `qwen-blog` | [Qwen Blog](https://qwen.ai/blog) | `primary` | Models, Multimodal, Open Source, Agents | First-party releases; confirm weights, licenses, and serving availability on concrete pages. |

## AI coding, agents, and open-source engineering

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `github-copilot-changelog` | [GitHub Copilot Changelog](https://github.blog/changelog/label/copilot/) | `primary` | AI Coding, Agents, Products | Product changes and availability; marketing examples do not prove productivity gains. |
| `cursor-changelog` | [Cursor Changelog](https://cursor.com/changelog) | `primary` | AI Coding, Agents, Products | Product releases and rollout details; check plan, platform, and preview limitations. |
| `openai-codex-releases` | [OpenAI Codex Releases](https://github.com/openai/codex/releases) | `primary` | AI Coding, Agents, Developer Tools | Concrete version changes; routine fixes alone may not meet the value threshold. |
| `claude-code-releases` | [Claude Code Releases](https://github.com/anthropics/claude-code/releases) | `primary` | AI Coding, Agents, Developer Tools | Concrete version changes; separate shipped behavior from documentation or preview notes. |
| `gemini-cli-releases` | [Gemini CLI Releases](https://github.com/google-gemini/gemini-cli/releases) | `primary` | AI Coding, Agents, Developer Tools | Concrete version changes; filter release noise and check migration notices. |
| `hugging-face-blog` | [Hugging Face Blog](https://huggingface.co/blog) | `primary` | Open Source, Models, Data, Agents, Inference | Mixes staff and community posts; identify the author and follow links to original artifacts. |
| `github-engineering` | [GitHub Engineering](https://github.blog/engineering/) | `builders` | AI Coding, Agents, Engineering Practice | First-hand software engineering and platform practice; supplier perspective still needs scope and failure checks. |
| `pytorch-blog` | [PyTorch Blog](https://pytorch.org/blog/) | `builders` | Training, Inference, Frameworks | Project and ecosystem engineering; benchmark claims retain hardware and workload conditions. |
| `langgraph-releases` | [LangGraph Releases](https://github.com/langchain-ai/langgraph/releases) | `primary` | Agents, Orchestration, Developer Tools | Release record for the project; do not infer production benefit from a feature alone. |
| `ollama-releases` | [Ollama Releases](https://github.com/ollama/ollama/releases) | `primary` | Local Models, Inference, Developer Tools | Release record for local model tooling; filter minor fixes unless materially useful. |

## People, intelligence, and discovery

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `arxiv` | [arXiv](https://arxiv.org/) | `discovery` | Research, Models, Reasoning, Agents | Search relevant `cs.AI`, `cs.CL`, and `cs.LG` categories, then cite the concrete paper page; a preprint is not peer review. |
| `metr-research` | [METR Research](https://metr.org/research/) | `intelligence` | Agents, Evaluation, Productivity, Safety | Third-party evaluation; preserve study design, sample, uncertainty, and disclosed relationships. |
| `simon-willison` | [Simon Willison](https://simonwillison.net/) | `people` | AI Coding, Agents, Models, Tools | First-hand experiments and analysis are individual evidence, not universal outcomes. |
| `lilian-weng` | [Lilian Weng](https://lilianweng.github.io/) | `people` | Agents, Reasoning, Research | Strong synthesis but low frequency; follow citations back to original papers. |
| `latent-space` | [Latent Space](https://www.latent.space/) | `intelligence` | AI Engineering, Agents, Industry | Interviews and analysis may reflect host, guest, employer, or investor interests. |
| `hacker-news` | [Hacker News](https://news.ycombinator.com/) | `discovery` | Developer Practice, Failures, Open Source | Leads and counterexamples only; popularity and comments are not evidence for a core fact. |

## Policy and standards

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `nist-ai` | [NIST Artificial Intelligence](https://www.nist.gov/artificial-intelligence) | `primary` | Standards, Evaluation, Risk Management | Official US standards and guidance; distinguish drafts, requests for comment, and final publications. |
| `eu-ai-office` | [European AI Office](https://digital-strategy.ec.europa.eu/en/policies/ai-office) | `primary` | AI Act, General-Purpose AI, Governance | Official EU implementation source; distinguish adopted law, guidance, proposals, and enforcement dates. |

## Using the list

Apply these rules after selecting topic-relevant entries:

1. A user-required source takes precedence, but never bypasses verification.
2. For a broad scan, consider relevant Frontier, Builders, and Voices material across multiple organizations and roles; use an `intelligence` or `discovery` path when it has relevant material.
3. For a narrow product task, the concrete official changelog, release, documentation, paper, or repository page is more useful than a publisher homepage.
4. If a discovery entry surfaces a claim, follow it to the original source. Do not use a search result, category page, feed item, or discussion thread as a substitute for the concrete evidence page.
5. Expand beyond this list when it lacks a relevant actor, geography, topic, opposing view, or direct source. Record material expansions in `task_note`.
6. An inaccessible or inactive preferred source is a disclosed coverage limitation, not a reason to invent a result or lower the verification standard.

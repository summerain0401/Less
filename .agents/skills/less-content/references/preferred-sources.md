# Less preferred sources

Use this list as the first search surface for discovery tasks. Select only entries relevant to the requested topic and time range. Sources outside the list remain allowed when they improve coverage or verification.

This list retains the concrete nodes from the original [Source Registry](../../../../operations/source-registry.json), while allowing later additions. Select entries across the original [Coverage Map and Source Map](../../../../docs/current/02-content-skill.md) as the task requires. `role` names a node's main editorial role; it does not determine the Brief source field `primary` and does not confer trust automatically:

- `primary`: an organization publishing its own releases, research, documentation, or repository changes.
- `people`: a person's first-hand thinking, experience, or long-form analysis within a specific area.
- `builders`: first-hand application workflows, reproducible methods, engineering practice, and failure reports.
- `intelligence`: professional reporting, research, interviews, or independent evaluation that adds context or challenges claims.
- `discovery`: a lead surface; follow a lead to the concrete original page before using it in a Brief.

Do not add collection intervals, health status, authority scores, or selection metrics here. For a publisher claim about performance, impact, price, or comparative advantage, attribute the claim and seek independent support when it affects the conclusion.

A person's blog and social account are one editorial node when they serve the same area of expertise. Follow the person's original posts for first-hand views or experience, and follow linked documents for product or research claims. Account visibility and follower counts are not selection criteria.

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
| `aisi-research` | [UK AI Security Institute Research](https://www.aisi.gov.uk/research) | `primary` | Frontier Evaluation, Safety, Agents, Research | Original government research; preserve methods and limits, and apply the Important threshold to specialized work. |

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
| `anthropic-engineering` | [Anthropic Engineering](https://www.anthropic.com/engineering) · [Claude Developers](https://claude.dev/) | `builders` | AI Coding, Agents, Context, Evaluation | Two first-party engineering surfaces; check both for relevant posts, and distinguish internal experience from generalizable results and shipped behavior. |
| `shopify-engineering` | [Shopify Engineering](https://shopify.engineering/latest) | `builders` | AI Coding, Agents, Engineering Practice | First-hand production workflows; retain the project's conditions and the company's own perspective. |
| `martin-fowler-gen-ai` | [Exploring Generative AI](https://martinfowler.com/articles/exploring-gen-ai.html) | `builders` | AI Coding, Agents, Engineering Practice, Voices | Named authors' experiments and reflections; check the author, method, and limits of each article. |
| `pytorch-blog` | [PyTorch Blog](https://pytorch.org/blog/) | `builders` | Training, Inference, Frameworks | Project and ecosystem engineering; benchmark claims retain hardware and workload conditions. |
| `opencompass` | [OpenCompass](https://github.com/open-compass/opencompass) | `primary` | Evaluation, Open Models, Multimodal, Developer Tools | Original evaluation framework and releases; a leaderboard result still requires the dataset and run configuration. |
| `langgraph-releases` | [LangGraph Releases](https://github.com/langchain-ai/langgraph/releases) | `primary` | Agents, Orchestration, Developer Tools | Release record for the project; do not infer production benefit from a feature alone. |
| `ollama-releases` | [Ollama Releases](https://github.com/ollama/ollama/releases) | `primary` | Local Models, Inference, Developer Tools | Release record for local model tooling; filter minor fixes unless materially useful. |

## Applications, work, and original views

These complement the engineering sources for general knowledge workers. Look for writing, research, office work, learning, creative practice, and team workflows. Case studies, authored essays, and interviews can support their own observed experience or expressed views; they do not establish universal benefits.

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `one-useful-thing` | [One Useful Thing / Ethan Mollick](https://www.oneusefulthing.org/) | `people` | Work, Learning, Applications, Voices | Author's experiments and views, not an independent product audit; preserve disclosed commercial relationships or promotions in the concrete article. Distinguish linked research from experience and predictions. Open the dated article; inaccessible or subscriber-only text remains a lead. |
| `microsoft-worklab` | [Microsoft WorkLab](https://www.microsoft.com/en-us/worklab) | `intelligence` | Work, Adoption, Productivity, Voices | Microsoft-funded research, interviews, and practical advice; preserve survey/sample limits and distinguish product promotion from independent evidence. Open the concrete report or interview; a landing page or inaccessible full record is only a lead. |

## Chinese ecosystem, practice, and interviews

For broad scans, use Chinese queries as well as English queries. Include original Chinese experience, Chinese teams, local products, and local adoption; overseas news translated into Chinese alone is insufficient. Combine these entries with DeepSeek and Qwen above and expand to other relevant original sources. A language community is not a country filter: Chinese-language authors outside China can also add useful perspectives.

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `sspai-practice` | [少数派](https://sspai.com/) | `builders` | Applications, Writing, Research, Learning, Creative Work | Named authors' practical experience; verify the author, steps, version, limits, and sponsorship. Community articles vary in quality; headline recommendations or paid previews alone are not sufficient. |
| `latepost-interviews` | [晚点聊 / LateTalk](https://podcast.latepost.com/) | `intelligence` | Chinese AI, Products, Adoption, Industry, Voices | Original interviews and industry analysis; guests can have employer/investor interests. Read or listen to the relevant full record, or obtain a reliable transcript; show notes alone are leads. |
| `silicon-valley-101` | [硅谷101](https://sv101.fireside.fm/) | `intelligence` | Applications, Industry, Work, Society, Voices | Chinese-language original interviews with practitioners; separate host/guest claims and predictions, and check disclosed sponsorship and employer/investor interests. Audio or video must be accessible with verifiable context or a reliable transcript; summaries alone cannot substantiate a Brief. |
| `feishu-practice` | [飞书客户与实践案例](https://www.feishu.cn/customers) | `builders` | Office Work, Team Workflows, Adoption, Applications | Supplier-selected customer cases; attribute performance and efficiency claims to the vendor or named customer, keeping conditions and measured scope. Only AI-relevant cases qualify. Index pages may need following to a concrete dated case; no date means no assumption of recency. |
| `kimi-applications` | [Kimi 教程](https://www.kimi.com/academy/) · [帮助与产品动态](https://www.kimi.com/help) | `primary` | Chinese AI, Research, Documents, Slides, Applications | First-party application guides and product changes; separate demonstrated workflows from effectiveness claims. Open the concrete tutorial or announcement and establish its original date; undated help pages do not prove a new release. |
| `tencent-ima` | [腾讯 ima](https://ima.qq.com/) | `primary` | Chinese AI, Knowledge Work, Research, Writing, Applications | Product/help surface for the vendor's knowledge-work tool; follow to a concrete dated announcement or help record. Login-only knowledge bases and undated pages remain discovery leads, and vendor benefits require attribution. |

## People, intelligence, and discovery

| id | name and entry | role | topics | use and bias note |
| --- | --- | --- | --- | --- |
| `arxiv` | [arXiv](https://arxiv.org/) | `discovery` | Research, Models, Reasoning, Agents | Search relevant `cs.AI`, `cs.CL`, and `cs.LG` categories, then cite the concrete paper page; a preprint is not peer review. |
| `hugging-face-papers` | [Hugging Face Daily Papers](https://huggingface.co/papers) | `discovery` | Research, Models, Reasoning, Agents | Trending papers are leads; open the actual paper and artifacts, and do not treat votes as evidence. |
| `metr-research` | [METR Research](https://metr.org/research/) | `intelligence` | Agents, Evaluation, Productivity, Safety | Third-party evaluation; preserve study design, sample, uncertainty, and disclosed relationships. |
| `epoch-ai-publications` | [Epoch AI Publications](https://epoch.ai/publications) | `intelligence` | Frontier, Evaluation, Compute, Industry | Original analysis and measurements; check data, methods, uncertainty, and funding or commissioned-work context where relevant. |
| `artificial-analysis-evaluations` | [Artificial Analysis Evaluations](https://artificialanalysis.ai/evaluations) | `intelligence` | Models, Evaluation, Pricing, Agents | Direct measurements; preserve benchmark version, conditions, and disclosed commercial interests. |
| `simon-willison` | [Simon Willison](https://simonwillison.net/) · [X](https://x.com/simonw) | `people` | AI Coding, Agents, Models, Tools | First-hand experiments and analysis are individual evidence, not universal outcomes; merge duplicate blog and X posts. |
| `lilian-weng` | [Lilian Weng](https://lilianweng.github.io/) | `people` | Agents, Reasoning, Research | Strong synthesis but low frequency; follow citations back to original papers. |
| `interconnects` | [Interconnects / Nathan Lambert](https://www.interconnects.ai/) · [X](https://x.com/natolambert) | `people` | Open Models, Frontier, Industry, Voices | Original analysis and evolving judgments; separate evidence from predictions and follow cited artifacts. |
| `karpathy` | [Andrej Karpathy Blog](https://karpathy.github.io/) · [X](https://x.com/karpathy) | `people` | Models, AI Coding, Research, Voices | First-hand teaching, experiments, and views; long-form posts are low frequency and short posts need full context. |
| `tibo-codex-x` | [Tibo Sottiaux / X](https://x.com/thsottiaux) | `people` | Codex, AI Coding, Agents, Products | First-hand Codex direction and product clarifications; verify rollout, access, and performance in official materials. |
| `boris-cherny-x` | [Boris Cherny / X](https://x.com/bcherny) | `people` | Claude Code, AI Coding, Agents, Products | First-hand Claude Code explanations; verify shipped behavior in documentation or releases. |
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
2. For a broad scan, separately search application practice, substantive views/interviews, and important capability changes with both Chinese and English queries. Check relevant sources in both communities across organizations and roles; record actual sources checked and coverage/access gaps in `task_note`, without language or Brief quotas.
3. For a narrow product task, the concrete official changelog, release, documentation, paper, or repository page is more useful than a publisher homepage.
4. If a discovery entry surfaces a claim, follow it to the original source. Do not use a search result, category page, feed item, or discussion thread as a substitute for the concrete evidence page.
5. Expand beyond this list when it lacks a relevant actor, geography, topic, opposing view, or direct source. Record material expansions in `task_note`.
6. An inaccessible or inactive preferred source is a disclosed coverage limitation, not a reason to invent a result or lower the verification standard.
7. For a social post, open the concrete post and check author, date, full wording, and surrounding thread. A person's own view or direct experience can be primary for that narrow claim; reposts, teasers, and product-effect claims require the linked original material or corroboration. If only a search snippet is visible, use it as a lead and report the access limit.
8. Deduplicate the same claim across a person's blog, social account, and official announcement. Signals come from comparing supported material across events, not from a required social account or source count.

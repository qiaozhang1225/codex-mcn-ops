# Codex MCN Ops PRD

## Positioning

`codex-mcn-ops` is a Codex-first operations repo for IP building and matrix publishing. It exists to help one operator run the full loop: collect material, make content, prepare platform-specific publish packages, publish through Android apps, and review results.

The product is not a web app. The first usable version is a repo of executable workflows, a small SQLite ledger, ADB publishing utilities, and Feishu handoff payloads.

## Goals

- Keep the operating system simple enough for Codex to understand and execute.
- Make every publishing action auditable through local logs, screenshots, and SQLite rows.
- Use real phone apps for publishing instead of paid APIs or private web publishing endpoints.
- Keep human confirmation before final publish unless explicitly disabled.
- Reuse the useful MXNZP/SQLite/CLI material collection work from the deprecated project without carrying over its Web center or DeepSeek dependency.

## Non-goals

- No React/FastAPI local backend.
- No AiToEarn API, MCP, or Electron private-interface route.
- No platform private web API adapter in V1.
- No autonomous publish without an explicit live command.
- No DeepSeek client or provider-specific understanding table; material understanding is part of the default collection workflow and is stored as `codex-agent/gpt-5.5/success` metadata unless an explicit rules fallback is requested.

## Core Workflows

- Material collection and evaluation.
- Content package creation.
- Platform publish preparation.
- Android ADB publish execution.
- Feishu confirmation and reporting.
- Manual or semi-automatic tracking snapshots.

## Material Collection Policy

Search is a required stage before transcript extraction. Keywords may be provided by the operator or selected by Codex from the IP role positioning, but both paths must pass through the same search prefilter.

The search prefilter decides which videos deserve the more expensive speech-to-text step. It evaluates:

- title and caption relevance to the keyword / IP role
- public heat, especially likes, saves, comments, and shares
- duration fit, with a default acceptable range of 20 to 300 seconds
- whether the current search page is still strong enough to justify fetching the next page
- whether enough candidate material already exists for the target count

The prefilter is not the final content judgment. It exists to reduce wasted API calls and give Codex a smaller, higher-quality set of videos for transcript extraction and material understanding.

## Success Criteria

V1 is successful when one real content package can be prepared, pushed to a connected Android phone, driven to the final publish confirmation screen for Douyin/Xiaohongshu/WeChat Channels/Kuaishou, captured as proof, and recorded back to SQLite and Feishu payloads.

For material collection, V1 is successful when one command can search Douyin through MXNZP, store candidates and skipped reasons, extract transcript text, write material understanding metadata, match the material to IP roles, and promote a reviewed material into a `content_packages` draft.

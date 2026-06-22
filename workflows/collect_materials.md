# Workflow: Collect Materials

## Intent

Collect candidate material for an IP without turning the project into a backend system. MXNZP only fetches Douyin data; Codex/GPT-5.5 performs understanding, matching, and review.

## Inputs

- IP role or positioning
- target topic and search keywords
- desired count
- `mock` or `mxnzp` provider

## Steps

1. Read `ip_roles` and decide the topic, keywords, avoid terms, and target count.
2. Run `mcn collect run --topic ... --tool-provider mock|mxnzp`.
3. Review `collection_candidates` statuses: `saved`, `below_threshold`, `rejected`, `skipped`.
4. Run or rerun `mcn collect understand --run-id ... --provider codex --model gpt-5.5` when Codex needs to refresh the understanding JSON.
5. Run `mcn collect match --run-id ...` to score materials against active roles.
6. Review `mcn collect report --run-id ...`.
7. Promote only reviewed materials with `mcn material promote --material-id ... --platform douyin`.

## Output

- Material list
- Fit notes
- Suggested content angles
- Skipped reasons and next collection keywords

## Understanding JSON

Every saved material must have:

- `topic_summary`
- `hook`
- `core_claim`
- `content_structure`
- `audience`
- `emotion_trigger`
- `rewrite_angles`
- `risk_notes`
- `usable_quotes`
- `recommended_platforms`
- `role_fit_notes`
- `next_collection_keywords`

## Safety

- Start real MXNZP collection with `--target-count 1`.
- Never store API secrets or cookies in SQLite logs.
- DeepSeek is not part of this project; do not add DeepSeek imports, environment variables, or logs.

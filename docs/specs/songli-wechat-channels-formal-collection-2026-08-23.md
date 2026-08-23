# Song Li WeChat Channels Formal Collection — 2026-08-23

## Outcome

The Windows WeChat Channels collector is now integrated with the existing Mac
collection ledger. Formal run `crun_8ffa8a1201f8` completed with 245 persisted
unique candidates and five material results: four new transcripts and one
idempotently reused material.

The final controlled sample used five business keywords, one page per keyword,
a 100-like floor, and a 20–300 second duration window. The provider captured
250 raw results from 213 accounts. It reported `source_exhausted=false` and
`stop_reason=max_pages`, so this run is not represented as a complete traversal.

## Implemented path

```text
Mac collection CLI
  -> authenticated LAN Hub
  -> Windows hardened wx_channel worker
  -> WeChat Channels keyword search and detail API
  <- stable work identity and short-lived media lease
Mac
  -> temporary media download and decryption
  -> FFmpeg normalization
  -> Qwen ASR
  -> eligibility and material understanding
  -> SQLite source work, observation, candidate, transcription, material,
     role match, tool-call audit, and run summary
```

All discovered candidates are persisted before selection. Signed media URLs,
decode keys, worker credentials, and Hub credentials are excluded from durable
records. The media file is deleted after transcription.

## Live acceptance

- final run status: `completed`
- candidates: 245
- material results: 5
- new transcripts: 4
- reused transcripts: 1
- database integrity: `ok`
- foreign-key issues: 0
- logical sensitive-data scan: passed
- full test suite: 184 passed
- Windows post-run certificate count: CurrentUser 0, LocalMachine 0
- Windows post-run worker/listeners/media: 0 / 0 / 0

The original acceptance cycle produced six complete Channels materials. A
subsequent product decision raised the viral-material floor from 100 to 2,000
diggs. Four materials below the new floor and their transcripts, derived
understanding records, role matches, material observations, and ASR cache rows
were removed. Search candidates, works, authors, metrics, and run history remain
available for audit. The main database now contains 293 unique Channels works,
252 authors, two complete Channels materials, and two transcripts.

## Quality boundary

The existing material-understanding and role-match behavior is intentionally
the same rules-based path used by Douyin. It extracts hook, claim, structure,
risk, and rewrite clues, but it is not a deep semantic review. Neither of the
two viral materials remaining after the 2,000-digg cleanup currently receives
an automatic `accepted` match for the Song Li role. General material
persistence and role-specific acceptance remain separate states.

The next quality stage should replace exact-term role matching with an
evidence-bearing semantic decision while retaining the exact rules as a
fail-closed baseline.

Formal Channels collection now also rejects any configuration with a digg
floor below 2,000 before a run record or remote search is created. The earlier
100-digg floor remains visible only in historical run evidence.

## Durable evidence

The sanitized run package is stored at:

`/Users/qiaoz-macmini/Projects/codex-mcn-ops/runs/channels/crun_8ffa8a1201f8`

It contains the manifest, candidate JSONL, material/transcript JSONL, complete
account rollup, and logical safety scan. The pre-run database backup is:

`/Users/qiaoz-macmini/Projects/codex-mcn-ops/data/backups/mcn_ops-before-channels-songli-20260823T145237.sqlite`

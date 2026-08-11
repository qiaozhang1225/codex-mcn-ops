# Hook Playbook

`hook_enhancement` protects and, only when necessary, sharpens the source's proven reason to stop.

## Core Decision

Judge the hook by its job, not by a preferred hook type or sentence pattern:

- who it attracts;
- what emotion or conflict makes the viewer continue;
- what promise it creates for the body;
- what speaker position makes it credible.

If the existing hook already performs that job, keep it or make only a surface-level oral adjustment.

## Preservation And Translation

- Do not replace a strong hook for novelty, politeness, duplication anxiety, or early risk cleanup.
- When the target IP can credibly use the source speaker position, prefer literal or near-literal preservation.
- When the speaker position is incompatible, use `perspective_translation` and record the reason.
- Translation must pass strength parity: conflict, specificity, intended-audience entry, emotional force, and reason to continue remain comparable.
- If those qualities cannot survive translation, return to material selection instead of accepting a weaker opening.

## Discomfort And Objection

A hook may work because the intended viewer disagrees with it. That resistance is not automatically a flaw.

Preserve deliberate provocation when it is relevant and supportable. The body must then handle the core objection without retracting the content task or turning the script into a different argument.

When the stopping power comes from a clear stance, judge preservation by attitude parity as well as semantic similarity. Replacing “what I firmly believe” with a warning, information gap, or neutral consequence changes the hook mechanism even if the topic stays the same.

## Stage Boundary

- Hook enhancement may correct ASR, rhythm, reference, speaker compatibility, or small duplication.
- It must not change body logic, add a new explanatory angle, or perform risk cleanup.
- Risk inside the hook is recorded for `risk_cleanup`; only the unsafe span may later change.

Record `hook_diff_type` as `unchanged`, `punctuation_asr`, `minimal_dedup`, `perspective_translation`, or `replaced`. `replaced` requires a documented incompatibility and should otherwise fail.

# Publish Format Playbook

`publish_format` packages the already-cleaned copy for release. It must not rewrite the正文.

## Responsibilities

- Generate a four-character cover title.
- Generate an eighteen-character video title.
- Generate a short video description.
- Generate a pinned comment only when it follows naturally from the content.
- Return the final copy and body character count.

## Hard Boundaries

- `final_copy` must equal the `risk_cleanup.cleaned_body`.
- Do not improve, shorten, expand, reorder, or re-risk-clean the body.
- If the body has a problem, send the task back to the earliest invalid stage instead of fixing it here.

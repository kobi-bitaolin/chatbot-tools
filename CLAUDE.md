# chatbot-tools

Tool-calling chatbot API (take-home assessment). Workflow: `/spec-driven-dev`. Resume from `docs/STATUS.md`.

## Separation of concerns (NFR-12)
- New code goes in the layer that owns the job: see `docs/chatbot-architecture.md` §2.1.
- Imports go one way: api → services → (tools, llm, models). Only `app/main.py` wires layers together.
- `tests/test_architecture.py` (AC-59) enforces the import rules; never weaken it to make code pass.
- Before each merge, state which layer every new or changed file belongs to.

## Conventions
- Spec first, test first: no code without an FR/NFR, no FR/NFR without an AC test (`test_ac_N_...`).
- One branch per task, one commit per task, Conventional Commits with IDs. Merges need the user's yes.
- No secrets in the repo; keys come from `.env` (git-ignored).

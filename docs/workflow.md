# Workflow

## Branches

| Branch | Purpose | Who updates it |
|---|---|---|
| `main` | Approved state. What a visitor sees. | Only by merging `dev`, and only when the owner asks. |
| `dev` | Integration branch. All work lands here first. | Commits and pushes while a step is being built. |

Rules:

1. Nothing is pushed to `main` directly. `dev` is merged into `main` when the owner says so.
2. Every commit is authored as the repo owner. No co-author trailers.
3. Work is planned in the evening and run during the day. The owner makes the decisions in conversation; each
   decision is recorded in `docs/decisions/` and collected in the
   [decision sheet](plan/decision-sheet.md). Only items marked `ready` in the [run queue](plan/queue.md) are built,
   one per run, from their spec file, following the run protocol there. The assistant does not decide.
4. Tests must pass on `dev` before it is merged into `main`.

## Releasing `dev` to `main`

```
git switch main
git merge --no-ff dev     # a merge commit keeps each release visible in history
git push origin main
git switch dev
```

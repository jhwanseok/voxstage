# Workflow

## Branches

| Branch | Purpose | Who updates it |
|---|---|---|
| `main` | Approved state. What a visitor sees. | Only by merging `dev`, and only when the owner asks. |
| `dev` | Integration branch. All work lands here first. | Commits and pushes while a step is being built. |

Rules:

1. Nothing is pushed to `main` directly. `dev` is merged into `main` when the owner says so.
2. Every commit is authored as the repo owner. No co-author trailers.
3. A step is only started when the owner asks for it (see the
   [rule-engine steps](plan/rule-engine-steps.md)). Each step begins with a decision brief; the
   owner decides, the decision is recorded in `docs/decisions/`, then the code is written.
4. Tests must pass on `dev` before it is merged into `main`.

## Releasing `dev` to `main`

```
git switch main
git merge --no-ff dev     # a merge commit keeps each release visible in history
git push origin main
git switch dev
```

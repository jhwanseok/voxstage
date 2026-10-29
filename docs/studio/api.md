# Studio API

FastAPI, JSON, prefix `/api/v1`. Resource paths use the domain slug (`bank`) for what all bots of a domain share (tools, slot lists) and the bot slug (`bank-en`) for everything else; a bot is one domain in one language (see data-model.md, "Bots"). The
OpenAPI document FastAPI generates is the exact contract; this page is the plan. Errors: `404` unknown resource,
`409` revision conflict, `422` input shape (Pydantic) or a failed publish (with a `ValidationReport`), `400` a
broken request that is not a shape error.

Write requests carry the row's `revision` (`If-Match` header or `revision` field). A stale value answers `409`
with the current row. Every response row contains `revision`.

## Session and users (slots)

| Method and path | Purpose |
|---|---|
| `GET /me` | The current user and roles. v1: the seeded local user, all roles. |
| `GET /roles` | The role names. Present so the UI can show role chips; there is no user management in v1. |

## Domains, bots and import

| Method and path | Request | Response |
|---|---|---|
| `GET /domains` | | domains with their bots |
| `GET /bots` | | bots: slug, domain, lang, title, `draft_revision`, `last_published_number`, `has_unpublished_changes`, `valid` |
| `GET /languages` | | the engine's languages (`voxstage/dataset.py` `LANGS`); a bot can only be made in one of them |
| `POST /bots` | `{domain, domain_title?, lang, title?, start: "empty" \| "copy", copy_from?: bot slug, settings?: {engine?, studio_only?}}` | `201` new bot: empty (with the language starter) or a copy of a sibling of the same domain in another language (structure copied, texts marked to translate). `domain_title` creates the domain when it does not exist. `409 {reason: "exists"}` for a taken domain and language, `{reason: "in_repo"}` for a new domain id that is a not-yet-imported folder of `domains/`; `422` for a bad id, language, copy source or setting. Design: `studio/frontend/src/mock/DESIGN-NOTES.md`, "새 상담봇 만들기" |
| `PUT /bots/{b}/translation` | `{faq: [ids], flows: [ids], notices: [ids]}` | what is still in the copied-from language; saving or deleting an entry or a flow takes it off by itself |
| `GET /bots/{b}` | | one bot plus counts per entity |
| `POST /domains/import` | `{source: "repo_domains" \| "upload", domain: "bank", replace: false}`; upload sends a zip | the domain and one bot per language directory found; `409` if it exists and `replace` is false |
| `GET /domains/{d}` | | the domain, its bots and shared-asset counts |

`repo_domains` reads `domains/<domain>/` of the checked-out repository from a configured root (server-side; the client
never sends a path). Import stores unknown files raw and returns a list of what was modelled and what stayed raw.

## FAQ (ST1)

| Method and path | Request | Response |
|---|---|---|
| `GET /bots/{b}/faq` | | entries in order, each with its pattern |
| `POST /bots/{b}/faq` | entry | created entry |
| `PUT /bots/{b}/faq/{entry_id}` | entry (question, answer, paraphrases, asr_variants, pattern) | entry |
| `DELETE /bots/{b}/faq/{entry_id}` | | `204` |
| `PUT /bots/{b}/faq/order` | `{ids: [...]}` | `204` |

Saves do not run the loader. Shape errors (wrong types, missing id/question/answer) answer `422`; the engine's rules
(at least 3 paraphrases and 1 ASR variant, a pattern per entry) are reported by validation, so a half-written entry can
be saved.

## Tools (ST1)

| Method and path | Request | Response |
|---|---|---|
| `GET /domains/{d}/tools` | | tools in order |
| `POST /domains/{d}/tools` | `{name, body}` | tool |
| `PUT /domains/{d}/tools/{name}` | body (`params`, `rules`, `default`, `risky`, `requires`, `verifies`, `retry`) | tool |
| `DELETE /domains/{d}/tools/{name}` | | `204`; `409` with the flows that call it unless `force=true` |

Rename is delete plus create; the response of `PUT` for a tool that flows use warns with the flow ids.

## Flows (view in ST1, edit in ST2)

| Method and path | Request | Response |
|---|---|---|
| `GET /bots/{b}/flows` | | list: id, start, node count, buttons, role, validation items for the flow |
| `GET /bots/{b}/flows/{id}` | | `{flow: {header, start, nodes, node_order}, layout: {viewport, direction, nodes: {id: {x, y}}}, graph: {nodes, edges}, items: [...]}` |
| `POST /bots/{b}/flows` | `{id, template?: "blank"\|"copy", copy_from?}` | new flow with `start` and one `end` node |
| `PUT /bots/{b}/flows/{id}` | the whole flow (header, start, nodes, node_order) | flow plus `items` (the studio's quick checks) |
| `PUT /bots/{b}/flows/{id}/layout` | `{viewport, direction, nodes: {id: {x, y, collapsed}}}` | `204`; does not change `revision` |
| `DELETE /bots/{b}/flows/{id}` | | `204`; `409` when another flow references it (`carry`, buttons are not references) or it is the verification flow while protected tools exist |

`graph` is derived by the server so the browser needs no copy of the node rules: `edges` come from the same table as the
engine's `NodeType.edges` (see screens, "Node kinds"), each as `{from, to, label, handle}`. The graph is a whole-flow
document, saved as a unit (the editor keeps the working copy in the browser and saves on demand and on idle). There
is no per-node endpoint.

`PUT` runs only the studio's quick checks: YAML-shape checks per node type (allowed keys from the loader's `ctx.only`
lists, required keys), edges point to existing nodes, one outgoing edge per handle, unreachable nodes. The loader is
authoritative and runs on validate.

## Notices and wording, settings (ST3)

| Method and path | Purpose |
|---|---|
| `GET/POST/PUT/DELETE /bots/{b}/notices[/{id}]` | Fixed notices: text, unique integer priority, optional `applies_when` |
| `GET/PUT /bots/{b}/wording` | The fixed set of situation keys; `PUT` takes all keys |
| `GET/PUT /bots/{b}/settings/{kind}` (bot) and `/domains/{d}/settings/{kind}` (shared: `sensitive_slots`, `readback_slots`) | `config`, `confirm`, `commands`, `corrections`, `confusions`, `sensitive_slots`, `readback_slots` |
| `GET/PUT /bots/{b}/files/{path}` and `/domains/{d}/files/{path}` | Raw files (also the policy files until the format is modelled) |

## Validation, publication, history

| Method and path | Request | Response |
|---|---|---|
| `POST /bots/{b}/validate` | `{}` | `ValidationReport` for the bot's current draft, including the domain's shared assets. Exports to a temp directory and runs the loader for this bot's language only. |
| `POST /bots/{b}/publications` | `{note}` | `201` publication. Runs validation first; with errors: `422` and the report, nothing is written. Needs the `publisher` role (v1: always true). |
| `GET /bots/{b}/publications` | | list newest first: number, note, kind, published_by, published_at, file count |
| `GET /bots/{b}/publications/{n}` | | publication with its files (paths and sizes) |
| `GET /bots/{b}/publications/{n}/files/{path}` | | file content |
| `GET /bots/{b}/publications/{n}/diff?against={m \| "draft"}` | | per-file status (added, removed, changed) and unified diffs of the exported text |
| `POST /bots/{b}/publications/{n}/rollback` | `{note, discard_draft: false}` | `201` new publication of kind `rollback`; the draft is reset to it. `409` when the draft has unpublished changes and `discard_draft` is false |
| `GET /bots/{b}/publications/{n}/export.zip` | | the files as a zip |

Flow of a publish: validate (engine loader on a temp export of this bot; the optional sibling check is a warning and never blocks) then, only if no errors,
compute `content_hash`; if equal to the newest publication, answer `409 nothing to publish`; otherwise store
`publication` and `publication_file` in one transaction, write the export directory (temp directory and rename), set
`bot.last_published_number`. A crash between the transaction and the rename is repaired at startup by
re-exporting the newest publication.

## Preview (ST3)

| Method and path | Request | Response |
|---|---|---|
| `POST /bots/{b}/preview/sessions` | `{source: "draft" \| publication number, setup?: {customer, policy, now}}` | session id; draft sources are exported to a temp directory and loaded; invalid drafts answer `422` with the report |
| `POST /preview/sessions/{id}/turns` | `{text}` or `{button}` or `{digits}` | `{reply, actions, trace, state}` from the engine's flow manager (`trace` is the engine's own trace) |
| `DELETE /preview/sessions/{id}` | | `204` |

Sessions are in memory. The manager is the one `interpreter.py` builds; the studio passes the same stateless state
object back each turn (ADR 0002), so no engine change is needed.

## Not in v1

Authentication (the `Authorization` header is ignored), user management, comments, multi-user locking beyond the
`revision` check, audio preview.

Shared assets: tools and the slot lists belong to the domain, so `PUT /domains/{d}/tools/{name}` changes what every bot of the domain will export. The response lists the bots it affects, and their validation goes stale (`shared_revision`, see data-model.md).

# Studio review of ADR 0014 (typed attributes, roles and API binding)

Reviewer: studio track, 2026-10-29. Draft read: `docs/decisions/0014-typed-attributes-roles-and-api-binding.md` at
`a0db543` (status proposed; A and B decided, C asked as Q53, D open). This note does not edit the ADR; the list in
"Proposed changes to the ADR" is for the engine worker. Studio screens for this ADR are ST4, built after the ADR is
accepted.

Data checked for this review (all three domains, `domains/*/tools.yaml` and `domains/*/ko/flows/*.yaml`): tool results
are flat maps (no list, no nested record); 29 `call` arguments, 28 of them a single placeholder (`"{order_id}"`), one
with a filter (`"{size | default('')}"`, an optional argument).

## 1. Type dictionary screen and the `types.yaml` round trip

Screen: a new menu **데이터** per bot (like **API 연결**, the content is shared by every language of the domain, and the
screen says so). A list of types; each opens a sheet with its fields (name, field type from the extractor list,
length, choices) or, for a scalar, its rule. A type that is in use shows where (roles, tool params, other types) and
cannot be deleted or renamed until those are changed (the same 409 pattern as deleting a tool that flows call).

Round trip:

- **Before ST4** nothing breaks: the importer keeps every file it does not model as raw text (`domain_file`) and the
  exporter writes it back unchanged, so a `types.yaml` added by the engine track publishes as is. The studio cannot
  edit it yet.
- **ST4**: `types.yaml` becomes a modelled shared setting (`domain_setting` kind `types`, one JSON document per domain,
  the same mechanism as `sensitive_slots.yaml`). Import parses it, export dumps it; the contract test
  (`tests/test_contract.py`: parsed YAML equals the source, and the engine loader accepts the export) covers it with no
  new test shape. Key order inside the file follows the stored order (types in the order written, fields in the order
  written), so a round trip does not reorder a hand-written file.
- An edit bumps the domain's `shared_revision`, so every bot of the domain needs validation again (as tools do today).
- Data migration: domains imported before ST4 hold `types.yaml` as a raw `domain_file` row; an Alembic data migration
  moves that row into `domain_setting(kind=types)`.

## 2. Roles

Screen: in the scenario editor, **시나리오 설정** gets a section **이 시나리오의 사람과 값** (roles of this flow) above the
trigger words, and a read-only line **통화 전체에서 쓰는 값** for session roles (today only `caller`, filled by the
identity check; decision B). Each flow role is one row: display name, type (select from the dictionary), and, when it
has a default, one sentence: "방문자는 먼저 '방문하실 분이 본인이신가요?'라고 물어, 예라고 하면 예약자 정보를 그대로 써요."
with the source role (select, same type only) and the question text editable.

Scope in the UI: flow scope is said as "이 시나리오 안에서만", session scope as "통화가 끝날 때까지 모든 시나리오에서".
The `ask` node form gains a pair of selects, 누구의 / 어떤 값 (role, then a field of its type), in place of the free slot
name; a flow without roles keeps the slot name field.

The default question is behaviour the user must see. If the engine asks it implicitly, the canvas draws it as a marker
on the first step that would ask for a field of that role ("먼저 본인인지 물어요"), so the call script stays honest. See
proposal P3.

## 3. API parameters and response schema

The subset in part 3 (type, enum, length, required) fits a form with one row per parameter: name, type (field types
plus named types, if P5 allows them), 필수 checkbox, length when the type is digits, choices when it is choice. The
response (`returns`) is a flat name-to-type map, which matches every tool in the three domains today; it is the same row
editor without the required flag. Nothing in the data needs arrays or nested objects, so the form does not have to
handle them in v1.

Two studio consequences:

- The fake API rules (`when`, `return`) can use the schema: the rule editor shows only declared params in `when` and
  declared fields in `return`, with typed inputs instead of free JSON text. A loader check of rules against the
  schema (P6) keeps the fake API and the spec from drifting.
- `params` changes shape from a list to a map; the studio reads both until every pack is migrated (Tools page, the
  call form's prefill).

## 4. Binding form in the `call` step

One row per parameter of the chosen API, required ones first, each with a source choice:

- **사람과 값** (role path): a select listing only role fields whose type matches the parameter, from the flow's roles and
  the session roles.
- **앞 API 결과**: results of earlier calls whose return field type matches. Calls that run on every path before this
  step are offered; calls that run on only some paths are listed disabled with the reason ("일부 경로에서만 불러요").
- **고정값**: a typed input (number, digits with length, choice select).

Values of the wrong type never appear in the selects; a stored binding that no longer matches (the type was edited) is
shown in the row as an error, not silently dropped.

Old template arguments: a row whose `args` value is exactly one placeholder (`"{order_id}"`, 28 of 29 today) is shown
as the slot binding the loader reads it as, with a small "예전 방식" tag and a one-click 바꾸기 that writes the new
binding. A template with more than a placeholder (`"{size | default('')}"`) stays a read-only template row with its
text, until P4 says how an optional parameter is written.

Renaming a step in the editor already rewrites the links to it; with binding by step id (`lookup.result.id`) the rename
must also rewrite bindings that name it (studio change in `lib/flowEdit.ts`, see P2).

## 5. Publish-check errors on the graph

| Error | Where it is drawn | In the panel |
|---|---|---|
| Required parameter not bound | Red ring and count on the `call` card | The parameter row in the binding form, with the source select focused |
| Type mismatch | Same | The row, "예약자 전화번호(전화번호)는 계좌 끝 4자리(숫자 4자리)에 넣을 수 없어요" |
| Collected on some paths only | The `call` card, and the edges of one path where the value is missing drawn in amber | "조건 2를 거쳐 오면 방문자 이름을 묻지 않아요" with a button that selects the step where an ask could go |

This needs the loader to return structured items (P1): code, node id, parameter, role and field, and for the path
error one witness path as a list of node ids. Today the loader stops at the first error per file (ST1 open item);
for a data-flow check that is too slow to work with, so all binding problems of a flow should be reported at once.

The editor's live checks before saving (`localProblems`) stay structural (links, start, end). The data-flow check runs
only in the engine, through validation, so the studio does not keep a second copy of the rule.

## 6. Studio database and migration

| Change | Storage | Migration |
|---|---|---|
| Type dictionary and session roles (`types.yaml`) | `domain_setting` kind `types` (JSON, revisioned) | data migration of an existing raw `types.yaml` row |
| Flow roles | `flow.header.roles` (JSON) | none |
| Typed tool params and `returns` | `tool.body` (JSON) | none; readers accept list and map |
| Bindings | `flow.nodes[*]` (JSON) | none |
| Display names of types, fields, roles | depends on the question asked as `ask studio` (in the file or studio-only) | a column or table only if studio-only |

Code changes, not schema: `FLOW_HEADER_KEYS` in `studio_backend/main.py` refuses unknown flow keys on save, so once
the engine accepts `roles` in a flow header the studio must add it there (and to `portable.FLOW_HEADER_ORDER` for the
export order) before anyone saves such a flow from the editor; until then such a save returns 422. This is the first
task of ST4, or a one-line fix earlier if the engine lands part 2 before ST4 starts.

## Proposed changes to the ADR (for the engine worker)

- **P1. Structured load errors.** The data-flow check of part 5 reports every problem of a flow, each with a code
  (`unbound`, `type_mismatch`, `not_collected`), node id, parameter, role and field, and for `not_collected` one
  witness path (node ids). The studio draws them as in section 5.
- **P2. Binding syntax.** Write down the exact YAML of a binding (for example `bind: {account_last4: {role: caller,
  field: last4}}`, `{call: lookup, field: id}`, `{const: "4821"}`), whether `args` and `bind` may both name one
  parameter (recommend no), and that an earlier call is named by its step id.
- **P3. When the default question is asked.** Say at which step the "Is the visitor you?" question happens (before
  the first ask of any field of that role, or as an explicit `confirm` step), and that the trace records it. If it is
  implicit, the studio shows it as a marker on that step; an explicit step would be simpler to draw and to test.
- **P4. Optional parameters.** A param with `required: false` replaces the template filter `default('')`; say what an
  unbound optional parameter sends (absent, or empty).
- **P5. Named types as parameter types.** Say whether a param can be a whole record (`Person`) or only a scalar field;
  the binding form differs (one row per record or per field).
- **P6. Fake API rules follow the schema.** The loader checks that `when` names declared params and `return` declared
  fields with the declared types.
- **P7. File locations and language.** Say where session roles live (`types.yaml` with the types is the suggestion)
  and where flow roles live (the flow header, a new key `roles`). Texts in a role (the default question) are
  per language, so they belong in the flow files, which are already per language; `types.yaml` stays language-neutral.
- **P8. Display names.** The model has only identifiers (`Person`, `booker`, `last4`); the studio and the read-back of
  R9 need human names per language. Whether they live in the files is asked to the owner (studio question); the ADR
  should allow an optional `label: {ko: ..., en: ...}` if the answer is "in the file".
- **P9. Consequences section.** Add: the studio stores `types.yaml` as a modelled shared setting, and until ST4 it
  round-trips the file unchanged (no studio work blocks parts 1 and 2 of the engine).

## Questions for the owner (studio)

Asked one at a time with `ask studio`, after Q53 (C) and not overlapping it or D:

1. Display names of types, fields and roles: in the files (`label` per language, exported, also usable by read-back),
   or studio-only? Recommendation: in the files.

## Owner decisions for ST4 (2026-10-29)

- Q54: display names live in the YAML files as a `label` per language. The studio reads them from the files and exports
  what is edited back into the files (no studio-only table; the "display names" row of section 6 needs no migration).
- Q55: no nesting in v1; a field is a scalar. The type form offers only scalar field types, and a parameter of a named
  type is bound field by field (see P5).

ST4 starts after ADR 0014 is accepted.

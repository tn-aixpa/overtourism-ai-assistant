# Integrated page context (visual context)

In **integrated mode** the assistant is embedded in the Angular application. Besides
the business entities the host is focused on, it can now see **what the user is
looking at**: a structured snapshot of the current page.

## 1. Business context vs. visual context

| | Business context | Visual context |
|---|---|---|
| State | `state.cognitive.current_context` | `state.page_context` |
| Content | ids of problems / proposals / scenarios | route, title and UI elements of the page |
| Sent via | `context` form field of `/agent/init` and `/agent` | `page_context` field of `/agent/init`, and `POST /agent/context` |
| Reaches the LLM | **only through tools**, e.g. `get_data_from_context()` / `get_context_details` | as a delimited prompt block (section 8) |
| Meaning | the data itself lives in the backend | a snapshot of the frontend |

They remain separate. `entities.scenario_id` seeds
`current_context["scenarios"]` only when no scenario is already selected.
`entities.territory` seeds the session's territory only when it is in the
authenticated user's allowed-territory list; a territory change clears cached
territory-scoped data. A user can explicitly name another allowed territory in
a request; that territory takes precedence for lookup even in integrated mode,
and data cached for the previous territory is cleared. The snapshot continues
to describe the page currently shown, so its entity IDs must not be reused for
lookups in the newly requested territory. Other page entities do not change
business context. Not to be confused with the pre-existing, unrelated
`state.integrated_context` field.

## 2. New `AgentState` attributes

* `page_context: Optional[dict]`: the validated, normalised snapshot (`None` if none was sent).
  Replaced wholesale, never edited field by field.
* `page_context_version: int`: server-side count of accepted snapshots (0 = none). Used
  internally so a finishing turn cannot roll back a newer snapshot.

## 3. Schema (version `1.0`)

```json
{
  "schema_version": "1.0",
  "captured_at": "2026-11-06T12:00:00Z",
  "route": "/proposals/edit/123",
  "page_title": "Edit proposal",
  "page_description": null,
  "revision": 17,
  "entities": {
    "territory": "molveno",
    "problem_id": "p1",
    "proposal_id": "pr1",
    "scenario_id": "s1",
    "active_tab": "Parcheggi"
  },
  "elements": [
    {"id": "proposal-name", "type": "textbox", "label": "Proposal name",
     "value": "New infrastructure plan", "visible": true, "enabled": true},
    {"id": "parking-capacity", "type": "number", "label": "Posti auto",
     "param_name": "parking_capacity", "value": 2.5},
    {"id": "territorial-index", "type": "chart", "label": "Indice turistico",
     "index_id": "tourism-index", "start_date": "2023-01-01",
     "end_date": "2023-12-31", "granularity": "annuale"},
    {"id": "scenario-plot", "type": "chart",
     "label": "Diagramma di Sostenibilità", "chart_type": "sustainability",
     "chart_subsystem": "Parcheggi"},
    {"id": "proposal-status", "type": "dropdown", "label": "Status",
     "selected": "Under review", "options": ["Draft", "Under review", "Approved"]},
    {"id": "save-button", "type": "button", "label": "Save", "enabled": false,
     "error": null, "group": "Actions"},
    {"id": "tasks", "type": "table", "label": "Tasks", "columns": ["Name", "Owner"],
     "rows": [["Survey", "Ann"]], "row_count": 340}
  ]
}
```

Models: `PageContext` / `PageElement` in `app/schemas.py`.

| Field | Notes |
|---|---|
| `schema_version` | optional, default `"1.0"`; any `1.x` accepted, other majors rejected |
| `route` | **required**, 1-512 chars. Send the path without query string (it may carry tokens/PII) |
| `captured_at` | optional ISO-8601 datetime |
| `page_title`, `page_description` | optional |
| `revision` | optional integer ≥ 0, **increasing per session** (a persisted counter or epoch ms). Enables stale-update protection (section 7) |
| `entities` | optional identifiers and selected page state: selected territory, scenario/proposal/problem IDs, active tab, index ID, date period, granularity and selected territories. Values are bounded; selected territory is accepted only if authorized for the user; this is never a place for computed data |
| `elements[]` | optional, default `[]`, ≤ 150 |
| element `id`, `type` | required. `type` ∈ `textbox textarea number date checkbox radio switch dropdown multiselect button link tab heading text table list chart image other`. Map widgets not named here to `other` |
| element `label`, `value`, `selected`, `options`, `visible` (default true), `enabled` (default true) | optional. `value` is a string/number/bool (checkbox/switch state goes here); `selected` is a string or list of strings |
| element `param_name` | optional backend parameter key (the `name` returned by `get_configuration_parameters`) |
| chart `index_id`, `start_date`, `end_date`, `granularity` | optional territorial-index identifiers describing what is plotted |
| chart `chart_type`, `chart_subsystem` | optional scenario-plot display mode (`sustainability` / `tourist_load`) and selected subsystem label; capture the active UI setting, not data points or computed statistics |
| element `required`, `error`, `group` | optional: required flag, validation message shown by the UI, section the element belongs to |
| table `columns`, `rows`, `row_count` | `rows` is a bounded sample (≤ 25 rows × ≤ 20 columns); `row_count` is the real total |

**Extensibility:** unknown fields are silently dropped (so they never reach the LLM) and
minor versions (`1.1`, …) are accepted, so additive changes need no backend release.
Adding an element type requires extending the `PageElementType` literal.

> The frontend source is not part of the backend repository: the frontend must be
> aligned with this schema (field names above are authoritative).

## 4. `POST /agent/init`

New optional multipart field **`page_context`**: the snapshot as a JSON string.
`context` keeps its meaning; a page snapshot can be used when the page has no selected
business entity.

* Integrated: if present it is validated and stored (`page_context_version = 1`); an
  invalid one fails the call (422 / 413) and **no session is created**. `_apply_context()`
  runs as before, and `entities.scenario_id` seeds the scenario context only if no
  scenario was selected through `context`. Omitting the snapshot is allowed (older
  frontends).
* Standalone: `page_context` is **ignored without being validated**, exactly like
  `context` already is. Standalone sessions never have a page context.
* The session mode is fixed for the lifetime of the session.

## 5. `POST /agent/context`

Multipart form: `session_id`, `page_context` (JSON string). Header `Authorization: Bearer …`.
Called by the frontend on Angular route navigation. Order of checks:
authentication (`_authenticate`, 401) → session lock → ownership (`_assert_owner`, 404 for
unknown *or foreign* sessions) → integrated mode (400 otherwise) → payload validation
(413 too large / 422 invalid) → update.

It replaces `state.page_context`. If it contains `entities.scenario_id` and the business
context has no scenario yet, that ID seeds `current_context["scenarios"]`; an existing
scenario context is never replaced. It creates no turn, calls no LLM, starts no
background task, and does not touch conversation history, language, role, mode,
`force_role` or waiting state. It is allowed while a turn is running.

Response `200`:

```json
{"session_id": "…", "status": "updated", "applied": true,
 "revision": 17, "version": 3, "active_turn_id": null}
```

`status: "stale"`, `applied: false` (still HTTP 200) means a snapshot with an equal or
newer `revision` is already stored; `revision` then reports the stored one. A stale or
duplicate (retried) request is not an error, so it is not a 4xx. `active_turn_id` is the
running turn, if any; in that case the snapshot applies from the next turn.

| Status | Cause |
|---|---|
| 400 | session is standalone |
| 401 | missing/invalid token |
| 404 | unknown session or not owned by the caller |
| 413 | `page_context` larger than the byte limit |
| 422 | invalid JSON / schema (detail lists `loc` + `msg` only, never the submitted values) |

## 6. Persistence

The store of record is the in-memory session store (`memory._STATE_STORE`); the JSON
file under `logs/` is a best-effort debug dump that is never reloaded. The update is
applied to the stored state and then dumped through `persist_state`. **The dump contains
only a content-free summary of the page context** (route, element count, revision),
because page text may include what the user typed.

## 7. Concurrency

* Requests for one session are serialised by the existing per-session lock, so an update
  never interleaves with a turn *start*, nor with another update.
* A turn runs on its own copy of the state and replaces the stored state when it
  finishes. `remember_state` now keeps the newer `page_context` if one was stored while the
  turn ran (`page_context_version` comparison), so a mid-turn navigation is never lost,
  and nothing else is overwritten by an update. The comparison and the update run under a
  small mutex (`memory._STATE_MUTEX`; microseconds, no I/O) because the update runs on the
  event-loop thread and the commit on a pool thread.
* A turn sees **one consistent snapshot**: the one stored when it started. A snapshot that
  arrives mid-turn is used from the next turn.
* **Stale protection:** with a client `revision`, a snapshot whose revision is not greater
  than the stored one is ignored. This resolves out-of-order arrival of close navigations.
  Without `revision` (on either side) the last request to arrive wins. After a page reload
  the frontend must continue its counter above the last one it sent (or use epoch ms).

## 8. How it reaches the LLM

Prompts here are single user messages (no system role), and the business context is
never printed in them: it is used by tools. Page context is therefore added to the two
prompts that reason about the user's question, by
`app.utils.page_context.render_page_context_block`:

* the ReAct step (`app/prompts/react_reasoning.py`), which decides tools / answer;
* the final answer (`app/prompts/answer_generation.py`).

The block is empty outside integrated mode or when no snapshot exists, so standalone
prompts are byte-for-byte unchanged. The block tells the model that: it is a
non-live snapshot (values are those at capture time); to use it to interpret questions
about the interface; to keep apart *UI-displayed*, *stored business data (tools only)* and
*unknown*; to enrich page-related questions with available data tools before asking; not
to invent; and that the content is untrusted data. The router, the entity parser and
other classification calls do not receive it (a deliberate, easily revisited choice).

## 9. Alongside `get_data_from_context()`

Unchanged. The block adds a one-line hint such as "Business context: 1 proposals … stored
data comes only from the data tools". The model can read *what the page shows* from the
snapshot, call the usual tools for *what is stored* (e.g. `get_context_details`), and
combine them ("the page shows status *Under review*; the stored proposal says …").

## 10. Standalone isolation

`page_context` is never set, validated, rendered or accepted in standalone sessions;
`POST /agent/context` answers 400 for them.

## 11. Limits and security

| Limit | Value | On exceed |
|---|---|---|
| payload bytes (`PAGE_CONTEXT_MAX_BYTES`) | 65 536 | 413 |
| elements (`PAGE_CONTEXT_MAX_ELEMENTS`) | 150 | 422 |
| options per element / table rows / table columns | 50 / 25 / 20 | 422 |
| text: id, label, option, cell, title / value, description / route | 200 / 1000 / 512 chars | **truncated** with `…[truncated]` (a long textarea must not make the whole snapshot fail) |
| rendered prompt block (`PAGE_CONTEXT_MAX_PROMPT_CHARS`) | 10 000 chars | remaining elements omitted with a note |

Safeguards: strict schema with unknown fields dropped; control characters stripped;
unsupported element types rejected; page text is JSON-quoted on one line and `<` / `>` are
escaped so it cannot close or fake the `<page_snapshot>` block; the block states it is
data, not instructions, and it cannot add tools or change permissions (it is only text in
two prompts). Logs carry only session id, route, element count and revision; errors never
echo submitted values; the debug dump holds only a summary. Isolation relies on the
existing token + `_assert_owner` checks; ids inside the snapshot are labels, never
authorisation. Note Starlette limits a single form part to 1 MB before the 64 KiB check
runs; cap request bodies at the reverse proxy as well.

## 12. Examples

```bash
# integrated init with a page snapshot
curl -X POST $API/agent/init -H "Authorization: Bearer $T" \
  -F integrated_mode=true -F context=proposal:123 \
  -F 'page_context={"route":"/proposals/edit/123","revision":1,"elements":[{"id":"save","type":"button","label":"Save","enabled":false}]}'
# 201 {"session_id":"9f2c…", …}

# route navigation
curl -X POST $API/agent/context -H "Authorization: Bearer $T" \
  -F session_id=9f2c… \
  -F 'page_context={"route":"/scenarios","revision":2,"elements":[]}'
# 200 {"session_id":"9f2c…","status":"updated","applied":true,"revision":2,"version":2,"active_turn_id":null}

# the same request again (retry / out of order)
# 200 {"session_id":"9f2c…","status":"stale","applied":false,"revision":2,"version":2,"active_turn_id":null}

# standalone session
# 400 {"detail":"Page context is only supported in integrated mode"}
```
Angular: `const f = new FormData(); f.append('session_id', id); f.append('page_context', JSON.stringify(snapshot));`

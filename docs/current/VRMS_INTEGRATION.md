# Wiring `cogs/media.py` into the real VRMS API

**Status: implemented.** The recommended design below (collapse `approve` into starting the VRMS
job, a polling loop, `VRMSGateButton` for the two gates) is what's actually built in
`cogs/media.py` / `services/vrms_api.py` / `services/database.py` today — this doc is now the
reference for *how* it works and *why*, not a plan for someone else to execute. See
`docs/current/ARCHITECTURE.md#media-requests-and-the-vrms-api` for the short version and a real
gotcha found while building this (Fastify's empty-body handling — also noted below, in "New
pieces to build").

Original context, still accurate: this replaces the "there's no VRMS API yet" premise
`docs/current/ARCHITECTURE.md` was written under before a real one existed. The `media_requests`
table, `TRANSITIONS`, and the `MediaActionButton` dynamic-item pattern described there are the
foundation everything below builds on.

## What VRMS is, right now

VRMS (VeryRareMediaService) is a Node/TypeScript backend that takes a media request, searches
download providers, downloads/verifies/scans the release, identifies it, fetches metadata,
organizes it into a Jellyfin library, and updates Jellyfin — with two optional admin-approval
pause points along the way. It lives at:

```
C:\Users\vrkel\projects\VeryRareMediaService
```

(a sibling of this repo under `C:\Users\vrkel\projects\`). Read directly from there if you want
more than this doc covers — `docs/api.md`, `docs/approvals.md`, `docs/pipeline.md`,
`docs/providers.md` are the relevant ones. Its own `server/README.md` has run instructions.

**Current state, honestly:** the pipeline, queue, and API are fully built and tested (220
passing tests), but **no real credentials are configured yet** — no TMDB key, no qBittorrent/
SABnzbd instance, no Jellyfin server pointed at from VRMS's side. That means:

- You *can* build and test this integration today against a running VRMS dev instance
  (`cd server && npm run dev`, defaults to `http://localhost:8787`) — requests will enqueue,
  and you can verify the bot's API calls, status polling, and Discord UI all work correctly.
- A request will currently fail at the "search providers" stage (no download provider
  configured), which is an *expected*, verifiable failure for now — not a bug in your wiring.
- Nothing will actually download or reach Jellyfin until the user configures those on the VRMS
  side. Don't treat "it downloaded something" as the bar for done; treat "the API calls, status
  transitions, and Discord UI all behave correctly against the real (if empty) VRMS API" as the
  bar for done.

## Auth

If VRMS's `API_KEY` env var is set, every request needs it:

```
Authorization: Bearer <VRMS_API_KEY>
```

Add to this bot's `.env` / `config/settings.py` (following the existing `env_int`/plain
`os.getenv` pattern already there):

```
VRMS_API_URL=http://localhost:8787
VRMS_API_KEY=
```

## Field mapping — this bot's vocabulary vs. VRMS's

| This bot | VRMS | Note |
|---|---|---|
| `media_type`: `"movie"` \| `"tv"` | `mediaType`: `"movie"` \| `"show"` \| `"anime"` \| `"music"` | Map `"tv"` → `"show"` when calling VRMS. |
| `tmdb_id` (int) | `metadataId` (string) | `str(tmdb_id)`. **Always send this** — it makes VRMS's `fetchMetadata` stage use `getDetails()` directly instead of re-searching TMDB by title, so it can't land on a different same-titled result than the one the user picked in Discord. |
| `media_requests.status`: `pending → approved → downloading → completed` (+ `denied`/`on_hold`/`cancelled`) | VRMS job `status`: `pending → running → awaiting_release_approval → running → awaiting_final_approval → running → completed` (+ `failed`/`cancelled`) | See "Recommended state mapping" below — these don't line up 1:1 and don't need to. |

## The full sequence, end to end

1. User runs `/media request`, staff eventually click **Approve** on the request card (today:
   only changes `media_requests.status` locally). **This is where you call VRMS.**
2. `POST {VRMS_API_URL}/api/queue` with `{ title, mediaType, year, metadataId }`. Store the
   returned job `id` on the request row (new column — see below).
3. VRMS's pipeline runs: search providers → select release → **pauses**
   (`awaiting_release_approval`) with its candidate list attached.
4. Staff need to approve/deny that release *in VRMS*, not just in the bot's own local state —
   see "Surfacing VRMS's two gates in Discord" below.
5. Once approved, VRMS downloads, verifies, virus-scans, extracts, identifies, fetches metadata,
   then **pauses again** (`awaiting_final_approval`) with the matched metadata + a storage check.
6. Staff approve that too, VRMS organizes the file, updates Jellyfin, and the job reaches
   `completed` (or `failed` if something broke, or stays `awaiting_*` indefinitely if nobody
   acts — there's no timeout).
7. The bot's polling loop (see below) notices `completed` and updates `media_requests.status`
   to `"completed"`, same as the existing manual "Mark Completed" path does today.

## Recommended state mapping

The cleanest mapping collapses this bot's manual `approved → downloading` step into one thing:
**"Approve" already means "start it in VRMS."** Concretely:

- Remove (or repurpose) the standalone "Mark Downloading" button — VRMS's own release-approval
  gate is the real "should this actually download" checkpoint now, so making the admin click
  through two separate manual gates before VRMS even gets a chance to show its own candidate
  list is redundant.
- `apply_media_action()`'s `"approve"` handler: after the existing `update_media_request_status`
  call, also call a new `services/vrms.py` (or a new `services/vrms_api.py` — see below) method
  that does the `POST /api/queue` call and stores the job ID.
- If that call fails (VRMS unreachable, etc.), don't silently leave the request in `"approved"`
  with no way to retry — either surface an error to staff and leave it `"approved"` with a
  retry button, or add a distinct failure state. Your call; just don't let it go silently stuck.

This is a recommendation, not the only valid design — if you'd rather keep "Mark Downloading" as
an explicit second click (matching the *original* seam note in ARCHITECTURE.md), that works
too, just move the `POST /api/queue` call there instead of into `"approve"`.

## Surfacing VRMS's two gates in Discord

This is the part that doesn't exist in any form today. VRMS pausing a job is invisible unless
something polls for it. Recommended approach — same pattern `cogs/notifications.py` already uses
for Jellyfin/VRMS-systemd polling (a `@tasks.loop`), not a new webhook receiver (this bot doesn't
run a web server today, and VRMS's generic webhook notifier is a bigger lift than a poll loop for
a first pass):

1. A new loop (in `cogs/notifications.py` or a new `cogs/vrms_requests.py`) that, every N
   seconds, for every `media_requests` row with a `vrms_job_id` and status still `"downloading"`:
   - `GET /api/jobs/:id` — if `status == "completed"`, call `update_media_request_status(...,
     "completed")` and edit the card. If `"failed"` or `"cancelled"`, decide how you want to
     reflect that (a new bot-side status, or just an error note left on the `"downloading"` card
     — there's no existing bot status for "VRMS gave up").
   - If the job's `stage`/`status` indicates it's paused at a gate the card hasn't shown yet,
     edit the card to add the gate's info + new buttons (below).
2. New buttons, same `discord.ui.DynamicItem` pattern as `MediaActionButton` (`cogs/media.py`),
   with their own `custom_id` template so they don't collide with the existing
   `media:(?P<action>[a-z]+):(?P<request_id>\d+)` one — e.g.
   `vrms_gate:(?P<gate>release|final):(?P<action>approve|deny):(?P<request_id>\d+)`.
   - **Release gate card**: show the top candidate (title/resolution/source/seeders — see
     `GET /api/approvals/releases`), Approve/Deny buttons calling
     `POST /api/jobs/:id/approve-release` (empty body keeps VRMS's auto-pick) /
     `POST /api/jobs/:id/deny-release`. A "pick a different candidate" selector is a reasonable
     v2 — don't feel obligated to build a dropdown for every release candidate on the first pass.
   - **Final gate card**: show the matched title/year/poster from `GET /api/approvals/final`'s
     `metadata`, plus its `storage.hasEnoughSpace` (warn visibly if `false` — VRMS won't
     auto-block, it's just information). Approve/Deny call `approve-final`/`deny-final`.

## New pieces built

- **`services/vrms_api.py`** (kept separate from `services/vrms.py`, which stays purely
  `systemctl`-facing): `aiohttp`-based `VRMSAPIClient`, same shape as `services/tmdb.py` — one
  class, `from_settings()` classmethod, methods for `enqueue`, `get_job`, `cancel_job`,
  `list_release_approvals`, `approve_release(job_id, candidate_id=None)`, `deny_release`,
  `list_final_approvals`, `approve_final`, `deny_final`. Raises `VRMSAPIError` (a distinct class
  from the systemd wrapper's `VRMSError`) on non-2xx responses.

  **Gotcha found by testing live against a local VRMS dev instance** (not visible from reading
  the route source): Fastify rejects a POST with `Content-Type: application/json` and a *truly
  empty* body (`FST_ERR_CTP_EMPTY_JSON_BODY`, "Body cannot be empty..."), and *also* rejects one
  sent with no `Content-Type`/body at all (`FST_ERR_CTP_INVALID_MEDIA_TYPE`, "Unsupported Media
  Type"). A bodyless action — `cancel`, `deny-release`, `approve-final`, `deny-final`, or
  `approve-release` with no `candidateId` — needs an actual `{}` sent as the JSON body.
  `VRMSAPIClient._request()` handles this by defaulting `json` to `{}` whenever it's `None` on a
  non-GET call, and lets `aiohttp` set `Content-Type` only when there's an actual body (the
  client's `_headers()` never hardcodes it). If you're modifying this client, don't reintroduce a
  hardcoded `Content-Type` header or pass `json=None` through to `aiohttp` unchanged on a POST —
  either one reintroduces this bug.
- **`services/database.py`**: `vrms_job_id TEXT`, `vrms_gate_channel_id INTEGER`,
  `vrms_gate_message_id INTEGER` on `media_requests`, added via the additive-migration mechanism
  (`_MIGRATIONS`, since `media_requests` already shipped before these columns existed) — plus
  getter/setters matching the existing `set_media_request_message` style, and
  `list_media_requests_with_vrms_job()` for the polling loop.
- **`config/settings.py`**: `VRMS_API_URL`, `VRMS_API_KEY`, `VRMS_JOB_POLL_SECONDS` (plain
  `os.getenv`/`env_int`, matching `JELLYFIN_URL`/`TMDB_API_KEY`'s style).
- **`.env.example`**: document the two new vars.

## Testing without real downloads

1. `cd C:\Users\vrkel\projects\VeryRareMediaService\server && npm run dev` — boots on
   `:8787` with an in-place SQLite DB, no credentials needed to boot.
2. `curl http://localhost:8787/api/health` — confirm it's up.
3. Point the bot's `.env` at it, run `/media request`, approve it, confirm:
   - A job actually appears: `curl http://localhost:8787/api/queue`.
   - It fails at `search_providers` (expected, no download provider configured) — confirm the
     bot's polling loop handles a `"failed"` job sensibly rather than hanging forever waiting
     for a gate that will never come.
4. For a real gate-pausing test without a download provider, you can manually push a job into
   `awaiting_release_approval` via VRMS's own test suite pattern, or just wait until the user
   has a real qBittorrent/SABnzbd instance configured — at that point a real search will
   actually produce candidates and reach the gate for real. Don't block finishing the bot-side
   wiring on that being ready; the API contract won't change.

## Full endpoint reference

See `docs/api.md` in the VRMS repo for the complete list; the ones this integration needs:

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/api/queue` | `{ title, mediaType, year?, metadataId? }` → job |
| GET | `/api/jobs/:id` | job detail incl. `status`, `stage`, `metadata`, `errorMessage` |
| GET | `/api/approvals/releases` | jobs awaiting Gate A, with candidates |
| POST | `/api/jobs/:id/approve-release` | `{ candidateId?: string }` |
| POST | `/api/jobs/:id/deny-release` | — |
| GET | `/api/approvals/final` | jobs awaiting Gate B, with metadata + storage check |
| POST | `/api/jobs/:id/approve-final` | — |
| POST | `/api/jobs/:id/deny-final` | — |

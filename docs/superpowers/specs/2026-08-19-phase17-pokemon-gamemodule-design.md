# Phase 17 — Pokémon GameModule (FR27, #62)

## Goal

Add a Pokémon TCG `GameModule` to the existing pluggable game-module
system. Descriptive only — no rules enforcement, no pairing/tiebreak
changes (those are FR28/FR29, Phase 18).

## Background

`backend/app/games/` already has a `GameModule` ABC
(`base.py`), a `GenericGameModule` (`generic.py`), and a registry
(`registry.py`) wired into `routers/pods.py` (validates `game_slug` on
pod create/update) and `routers/entries.py` (calls
`validate_entry_metadata` on entry create/update). `test_games_registry.py`
already asserts `get_game_module("pokemon-tcg")` raises — this phase
makes it resolve instead.

Match points (Win=3, Tie=1, Loss=0) are already hardcoded in
`backend/app/formats/swiss.py` and `backend/app/tiebreak/owp_oomw.py`,
independently of any game module. Pokémon's handbook values (§5.3.2)
match these exactly, so no scoring change is needed. Per-module scoring
config is future ruleset-modularity work (ROADMAP.md §1), expected to
land alongside the MTG module (#49) — out of scope here.

No `best_of` / match-format field exists anywhere in the schema.

## Scope

### 1. `PokemonGameModule`

New file `backend/app/games/pokemon.py`:

- `slug = "pokemon-tcg"`
- Class attributes `WIN_POINTS = 3`, `TIE_POINTS = 1`, `LOSS_POINTS = 0`,
  documented as matching handbook §5.3.2 (not consumed by
  `swiss.py`/`owp_oomw.py` in this phase — see Background).
- `validate_entry_metadata(metadata: dict) -> None`: validates
  `decklist_url` (see below).
- Class or module docstring notes Bo1-by-default per handbook §5.5.6
  (organizer discretion, no enforcement).

Register in `registry.py`: `GAME_MODULES["pokemon-tcg"] = PokemonGameModule()`.

### 2. `decklist_url` validation

Optional key in `Entry.metadata_`. If present, must be a string matching
exactly one of:

- `https://my.limitlesstcg.com/shared/<id>`
- `https://limitlesstcg.com/decks/list/<id>`

Scheme must be `https`. Host match is exact (case-insensitive). Path
must start with `/shared/` (for `my.limitlesstcg.com`) or
`/decks/list/` (for `limitlesstcg.com`) followed by a non-empty
segment. No format assumption on `<id>` beyond non-empty. Anything else
(other Limitless paths, other domains, `http`, malformed URL) raises
`ValueError` — the existing `entries.py` router pattern turns that into
a 422.

Key absent from metadata → passes (not required).

### 3. Bo1-by-default — UI only

No schema change. When a pod's `game_slug == "pokemon-tcg"`, the Report
page shows a one-line note near the result form: reported as best-of-1
by default, organizer discretion per Play! Pokémon rules §5.5.6.

### 4. Frontend: game selector at pod creation

`frontend/src/api/pods.ts`'s `createPod` currently hardcodes
`game_slug: "generic"`. Change signature to accept `gameSlug: string`
(no default), caller supplies it. `EventDetail.tsx`'s pod-creation UI
gets a `<select>` (Generic / Pokémon TCG) next to the "Create Pod"
button, defaulting to `"generic"`.

### 5. Out of scope

- No `decklist_url` edit UI. Convention is backend-validated only;
  organizers set it via API/import. Only existing metadata edit UI is
  `display_name`.
- No scoring/tiebreak changes (Phase 18, FR28/FR29).
- No `best_of` field or per-module scoring wiring (future
  ruleset-modularity work, ROADMAP.md §1).

## Testing

- `backend/tests/unit/test_games.py`: `PokemonGameModule` accepts
  metadata without `decklist_url`, accepts both valid URL patterns,
  rejects wrong host, wrong path, `http` scheme, non-string, malformed
  URL.
- `backend/tests/unit/test_games_registry.py`: flip existing
  `get_game_module("pokemon-tcg")` raises assertion to a resolves-to-
  `PokemonGameModule` assertion.
- Router-level test: create a `pokemon-tcg` pod, create an entry with
  and without `decklist_url` (valid and invalid values).
- Frontend: selector renders and passes `gameSlug` through to
  `createPod`; Report page shows Bo1 note only when
  `game_slug === "pokemon-tcg"`.

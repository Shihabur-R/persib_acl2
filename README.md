# ACL2 Dashboard

A lightweight, real-time web dashboard for tracking AFC Champions League Two (ACL2) standings and fixtures. Built with Python and Flask, this application fetches live data and automatically localizes match kick-off times to the user's timezone.

## Features

### ACL2 Analytics & Simulation

- **Balance Meter (`/balance`):** Scores how similar two sides are (0–100) in three
  modes: squad composition, home vs away record, and head-to-head standings.
- **Scenario Duel (`/duel`):** Projects two match outcomes side by side and reports
  which is more advantageous and which produces a more even win/draw/loss record.
  Optional goal inputs override a contextual projection that blends home/away form,
  recent results and head-to-head evidence; small samples are shrunk toward the
  season average, and missing data falls back to plain averages.
- **Saved Picks (`/picks`):** Persists comparisons in SQLite with validation for
  empty, over-long, malformed, and duplicate entries.
- **Statistical Insights (`/insights`):** Two dataset findings — squad position
  distribution per club, and a per-group standings comparison (goal difference,
  points per game, gap to leader).
- **Knockout Stage (`/knockout`):** Read-only bracket. Slots fill only when a group has
  completed its fixtures *and* the official draw is published; otherwise every slot
  stays TBD with an explicit reason. The bracket widens automatically for cross-group
  fields (up to a round of 32). No manual pairings or simulated winners.

### Dashboard

- **Live Standings & Fixtures:** Points, results, and scheduling for Groups A–H.
- **Group & Status Filters (`/fixtures`):** Pick one group or `All`. `All` merges every
  group into a single chronological list, with undated fixtures sorted last. The
  `All` / `Played` / `Upcoming` status filter works in both modes.
- **Club Directory (`/clubs`, `/players`):** Group filters follow the groups that
  actually have data, so Groups A–D appear alongside E–H.
- **Auto Timezone Localization:** Converts UTC kick-off timestamps into the visitor's
  local timezone (WIB/WITA/WIT aware) using vanilla JavaScript.
- **Resilient Fallback:** Transient API failures are retried with a short backoff, then
  served from the last known good payload (`stale`), a bundled JSON snapshot, or an
  empty state — each labelled in the header and a visible banner. Fallbacks use a
  shorter cache TTL so recovery is picked up quickly without hammering a dead API.
- **Responsive UI:** Mobile-first layout across desktop and mobile devices.

## Tech Stack

- **Backend:** Python 3, Flask
- **Frontend:** HTML5, CSS3, Vanilla JS
- **Templating:** Jinja2

## Getting Started

### Prerequisites

- Python 3.8 or higher
- `pip` package manager

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Shihabur-R/persib_acl2.git
   cd persib_acl2
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   # On macOS/Linux
   python3 -m venv venv
   source venv/bin/activate

   # On Windows
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

Start the development server:

```bash
python app_v2.py  # ACL2 Analytics & Simulation (recommended)
# or run the legacy app: python app.py
```
*The application will be available at `http://127.0.0.1:5000/`*

For production deployment, it is recommended to use a WSGI server like Gunicorn:
```bash
gunicorn --workers 2 --bind 0.0.0.0:5000 app_v2:app
```

Set a real secret key in production (used for flash messages):

```bash
export FLASK_SECRET_KEY="your-random-secret"
```

### Running the Tests

```bash
venv/bin/python -m pytest tests/test_metrics.py -v
```

24 tests covering:

- TC-01..TC-05: squad balance scoring, empty-data handling, scenario projection,
  pick validation, and pick deletion.
- Scenario goals: manual input, average fallback, invalid/contradictory scorelines.
- Contextual projection: venue and head-to-head aggregates, shrinkage bounds,
  safe fallback when fixtures are missing.
- Knockout: TBD without a draw, incomplete groups, bracket propagation, and
  cross-group expansion up to a round of 32.
- Fixture listing: chronological merge with date fallback, status filters.
- Club directory: Groups A–H support, empty groups omitted.
- Data resilience: retry, stale-cache, snapshot, and empty-response handling.

## Project Structure

```text
├── app_v2.py            # ACL2 Analytics & Simulation routes (recommended entrypoint)
├── app.py               # Legacy dashboard application
├── data_sources.py      # Club/player reads, AFC API retry + cache + layered fallback
├── metrics.py           # Balance scores, contextual projection, fixture listing helpers
├── knockout.py          # Read-only knockout completion, seeds, slots, bracket
├── picks_store.py       # Saved-pick persistence and validation
├── database.py          # SQLite helpers (Groups A–H)
├── build_database.py    # Database seeding for Groups E–H squads
├── seed_west_groups.py  # Adds official Groups A–D clubs from the AFC API
├── acl2.db              # SQLite dataset (32 clubs; E–H squads, 513 players)
├── data/                # Bundled fallback snapshot (snapshot_east.json, Groups A–H)
├── docs/                # HANDOFF.md (working context) and SRS.md (original spec)
├── tests/               # Unit tests for metrics, knockout, and data resilience
├── requirements.txt     # Python dependencies
├── static/              # CSS, JavaScript, and image assets
└── templates/           # Jinja2 HTML templates
```

### Data & Seeding

Club, standings, and fixture data for all eight groups comes from the public AFC API;
nothing is invented. `data_sources.py` accepts Groups A–H and omits groups with no data.

To add the official Groups A–D clubs to the local database (idempotent — existing rows
are never modified):

```bash
venv/bin/python seed_west_groups.py --dry-run   # preview only
venv/bin/python seed_west_groups.py             # insert missing clubs
venv/bin/python seed_west_groups.py --snapshot  # also extend the offline snapshot
```

Current dataset: 32 clubs (4 per group, A–H). Detailed squads (513 players) exist for
Groups E–H only; the public API does not publish squads for A–D, so those club pages
state that squad data is not yet available rather than showing fabricated players.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)

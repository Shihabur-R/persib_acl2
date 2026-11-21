# ACL2 Dashboard

A lightweight, real-time web dashboard for tracking AFC Champions League Two (ACL2) standings and fixtures. Built with Python and Flask, this application fetches live data and automatically localizes match kick-off times to the user's timezone.

## Features

### ACL2 Analytics & Simulation

- **Balance Meter (`/balance`):** Scores how similar two sides are (0–100) in three
  modes: squad composition, home vs away record, and head-to-head standings.
- **Scenario Duel (`/duel`):** Projects two match outcomes side by side and reports
  which is more advantageous and which produces a more even win/draw/loss record.
- **Saved Picks (`/picks`):** Persists comparisons in SQLite with validation for
  empty, over-long, malformed, and duplicate entries.
- **Statistical Insights (`/insights`):** Two dataset findings — squad position
  distribution per club, and a per-group standings comparison (goal difference,
  points per game, gap to leader) — plus an explicit dataset-limitations section.

### Dashboard

- **Live Standings & Fixtures:** Points, results, and scheduling for East Zone Groups E–H.
- **Auto Timezone Localization:** Converts UTC kick-off timestamps into the visitor's
  local timezone (WIB/WITA/WIT aware) using vanilla JavaScript.
- **Resilient Fallback:** Uses a bundled JSON snapshot when the AFC API is
  unreachable or returns an empty payload, with a visible banner telling the user
  the data is a local snapshot. Failed responses are cached to avoid repeated timeouts.
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
python -m pytest tests/test_metrics.py -v
```

Covers TC-01..TC-05: squad balance scoring, empty-data handling, scenario
projection, pick validation, and pick deletion.

## Project Structure

```text
├── app_v2.py            # ACL2 Analytics & Simulation routes (recommended entrypoint)
├── app.py               # Legacy dashboard application
├── data_sources.py      # Club/player reads, AFC API + TTL cache, snapshot fallback
├── metrics.py           # Balance scores, scenario projection, statistical findings
├── picks_store.py       # Saved-pick persistence and validation
├── database.py          # SQLite helpers
├── build_database.py    # Database seeding
├── acl2.db              # SQLite dataset (16 clubs, East Zone squads)
├── data/                # Bundled fallback snapshot (snapshot_east.json)
├── tests/               # Unit tests for metrics and picks
├── requirements.txt     # Python dependencies
├── static/              # CSS, JavaScript, and image assets
└── templates/           # Jinja2 HTML templates
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)

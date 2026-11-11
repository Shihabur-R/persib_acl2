# ACL2 Dashboard

A lightweight, real-time web dashboard for tracking AFC Champions League Two (ACL2) standings and fixtures. Built with Python and Flask, this application fetches live data and automatically localizes match kick-off times to the user's timezone.

## Features

- **Live Standings:** Real-time points, wins, draws, and losses tracking.
- **Match Fixtures:** Up-to-date scheduling and match results.
- **Auto Timezone Localization:** Converts ISO 8601 timestamps from the API directly into the user's local browser timezone using vanilla JavaScript.
- **Resilient Fallback:** Implements gracefully handled mock-data failovers if the upstream API becomes unavailable or rate-limited.
- **Responsive UI:** Clean, mobile-first design that works seamlessly across desktop and mobile devices.

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
python app.py
```
*The application will be available at `http://127.0.0.1:5000/`*

For production deployment, it is recommended to use a WSGI server like Gunicorn:
```bash
gunicorn --workers 2 --bind 0.0.0.0:5000 app:app
```

## Project Structure

```text
├── app.py               # Main Flask application and routes
├── requirements.txt     # Python dependencies
├── static/              # CSS, JavaScript, and Image assets
└── templates/           # Jinja2 HTML templates
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)

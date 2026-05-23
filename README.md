# Playlist Feed

A personal dashboard for keeping up with what your friends are listening to on Spotify.

Spotify doesn't have a native way to follow friends' playlist activity, so this app fills that gap — showing you the most recently updated playlists from people you care about, along with the last track they added.

## Features

- **Friends feed** — see each friend's most recently updated public playlist, who added to it, and what track was last added
- **Following tab** — view playlists you follow on Spotify (owned by others) with the same recent-activity view
- **Friend detail panel** — click any friend to see their top 10 most recently added tracks across all their public playlists, with a 5-minute client-side cache so repeat views are instant
- **Spotify app links** — playlist and profile links open directly in the Spotify desktop app, with a fallback to the web player if the app isn't installed
- **Friend management** — add friends by Spotify user ID or profile URL, bulk import via paste or JSON file, and export your list
- **Followed artists** — quickly add artists you follow on Spotify to your friends feed

## Tech Stack

- **Backend:** Django 4.2
- **Spotify API:** [Spotipy](https://spotipy.readthedocs.io/)
- **Frontend:** Tailwind CSS (via CDN), vanilla JS
- **Auth:** Spotify OAuth 2.0 via session-backed token cache (no database needed)

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/your-username/fetch-spotify.git
cd fetch-spotify
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Set up a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Add `http://127.0.0.1:8000/callback/` as a Redirect URI

### 4. Configure environment variables

Create a `.env` file in the project root:

```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/callback/
SECRET_KEY=a-long-random-secret-key
```

### 5. Run the server

```bash
python manage.py runserver
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) and log in with Spotify.

## Notes

- Friends are stored locally in `friends.json` (excluded from git)
- Spotify removed user-following in late 2023, so friends must be added manually by user ID or profile URL
- The app proxies playlist recency by finding the most recently `added_at` track, since Spotify doesn't expose a playlist "last modified" timestamp

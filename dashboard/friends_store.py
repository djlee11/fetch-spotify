"""
File-backed persistence for the friend ID list.

Stored at <BASE_DIR>/friends.json so it survives session resets, cookie clears,
and server restarts. Format:

    {
        "friends": ["spotify_user_id_1", "spotify_user_id_2", ...]
    }

Reads are tolerant of a missing/empty/malformed file (return []).
Writes do an atomic replace to avoid corrupting the file on crash.
"""

import json
import os
import tempfile
from django.conf import settings


def _path():
    return os.path.join(settings.BASE_DIR, "friends.json")


def load_friends():
    """Return the persisted friend ID list, or [] if the file is absent/invalid."""
    path = _path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except (json.JSONDecodeError, OSError):
        return []

    friends = data.get("friends") if isinstance(data, dict) else None
    if not isinstance(friends, list):
        return []
    # De-dupe while preserving order, drop anything that isn't a string
    seen = set()
    cleaned = []
    for f in friends:
        if isinstance(f, str) and f and f not in seen:
            seen.add(f)
            cleaned.append(f)
    return cleaned


def save_friends(friend_ids):
    """Atomically write the friend list to disk."""
    path = _path()
    payload = {"friends": list(friend_ids)}
    # Write to a temp file in the same directory, then rename — this avoids
    # leaving a half-written file if the process dies mid-write.
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".friends.", suffix=".json.tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup if the rename never happened
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def parse_user_id(raw):
    """
    Normalize a user-supplied string into a bare Spotify user ID.

    Accepts:
      - bare IDs:        "abc123"
      - profile URLs:    "https://open.spotify.com/user/abc123?si=..."
      - URI form:        "spotify:user:abc123"

    Returns the cleaned ID, or "" if the input is empty/garbage.
    """
    if not raw:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if "spotify.com/user/" in s:
        s = s.split("spotify.com/user/")[-1].split("?")[0].strip("/")
    elif s.startswith("spotify:user:"):
        s = s[len("spotify:user:"):]
    # Drop any remaining whitespace/quotes
    return s.strip().strip('"').strip("'")


def add_friend(uid):
    """Add a single friend ID. Returns True if added, False if already present."""
    friends = load_friends()
    if uid in friends:
        return False
    friends.append(uid)
    save_friends(friends)
    return True


def remove_friend(uid):
    """Remove a single friend ID. Returns True if removed, False if not present."""
    friends = load_friends()
    if uid not in friends:
        return False
    friends.remove(uid)
    save_friends(friends)
    return True

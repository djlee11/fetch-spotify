"""
Database-backed persistence for the friend ID list.

Replaces the previous friends.json file store so that friends survive
server restarts and deploys on cloud platforms like Render.
"""

from .models import Friend


def load_friends():
    """Return the persisted friend ID list in the order they were added."""
    return list(Friend.objects.values_list("user_id", flat=True))


def save_friends(friend_ids):
    """Replace the entire friend list (used by import and clear operations)."""
    Friend.objects.all().delete()
    for uid in friend_ids:
        if isinstance(uid, str) and uid:
            Friend.objects.get_or_create(user_id=uid)


def add_friend(uid):
    """Add a single friend ID. Returns True if added, False if already present."""
    _, created = Friend.objects.get_or_create(user_id=uid)
    return created


def remove_friend(uid):
    """Remove a single friend ID. Returns True if removed, False if not present."""
    deleted, _ = Friend.objects.filter(user_id=uid).delete()
    return deleted > 0


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
    return s.strip().strip('"').strip("'")

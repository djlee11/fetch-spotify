"""
Database-backed persistence for the friend ID list, scoped per Spotify user.

Each logged-in user has their own private list — rows are keyed by
(owner_id, user_id) so two users can independently follow the same person.
"""

from .models import Friend


def load_friends(owner_id):
    """Return the logged-in user's friend ID list in the order they were added."""
    return list(
        Friend.objects.filter(owner_id=owner_id).values_list("user_id", flat=True)
    )


def save_friends(owner_id, friend_ids):
    """Replace the entire friend list for this user (used by import / clear)."""
    Friend.objects.filter(owner_id=owner_id).delete()
    for uid in friend_ids:
        if isinstance(uid, str) and uid:
            Friend.objects.get_or_create(owner_id=owner_id, user_id=uid)


def add_friend(owner_id, uid):
    """Add a friend for this user. Returns True if added, False if already present."""
    _, created = Friend.objects.get_or_create(owner_id=owner_id, user_id=uid)
    return created


def remove_friend(owner_id, uid):
    """Remove a friend for this user. Returns True if removed, False if not present."""
    deleted, _ = Friend.objects.filter(owner_id=owner_id, user_id=uid).delete()
    return deleted > 0


def remove_all_friends(owner_id):
    """Delete all friends for this user — called on logout."""
    Friend.objects.filter(owner_id=owner_id).delete()


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

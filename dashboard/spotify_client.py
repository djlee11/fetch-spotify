"""
Spotify API helpers.

Key design decisions:
- Tokens are stored in Django's signed-cookie session (no DB needed).
- We use spotipy's SpotifyOAuth with a custom CacheHandler to bridge it
  with Django's session framework.

Spotify API limitations to be aware of:
- GET /me/following only supports type=artist (user-following was removed in Nov 2023).
  So "followed friends" must be added manually via the dashboard.
- Playlists have no "last modified" timestamp. We proxy recency by finding the
  most recently *added* track in each playlist (the added_at field on each track item).
"""

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheHandler
from django.conf import settings

SPOTIFY_SCOPE = "user-follow-read playlist-read-private"


# ---------------------------------------------------------------------------
# Session-backed token cache (no DB required)
# ---------------------------------------------------------------------------

class DjangoSessionCacheHandler(CacheHandler):
    """Stores the Spotify OAuth token inside Django's signed-cookie session."""

    def __init__(self, request):
        self.request = request

    def get_cached_token(self):
        return self.request.session.get("spotify_token_info")

    def save_token_to_cache(self, token_info):
        self.request.session["spotify_token_info"] = token_info
        self.request.session.modified = True


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_auth_manager(request):
    return SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
        cache_handler=DjangoSessionCacheHandler(request),
        show_dialog=False,
    )


def get_spotify_client(request):
    """
    Returns an authenticated spotipy.Spotify instance, or None if the user
    is not logged in.  Automatically refreshes expired tokens.
    """
    auth_manager = get_auth_manager(request)
    token_info = auth_manager.get_cached_token()
    if not token_info:
        return None
    if auth_manager.is_token_expired(token_info):
        token_info = auth_manager.refresh_access_token(token_info["refresh_token"])
    return spotipy.Spotify(auth=token_info["access_token"])


# ---------------------------------------------------------------------------
# Data-fetching helpers
# ---------------------------------------------------------------------------

def get_followed_artists(sp):
    """
    Returns all artists the current user follows (paginated).
    Each item is a Spotify Artist object dict.
    """
    artists = []
    result = sp.current_user_followed_artists(limit=50)
    while result:
        artists.extend(result["artists"]["items"])
        if result["artists"]["next"]:
            result = sp.next(result["artists"])
        else:
            break
    return artists


def get_latest_update_for_user(sp, user_id, max_playlists=8):
    """
    For a given Spotify user ID, finds the single most recently updated
    public playlist (proxied by the max added_at across the last batch of tracks).

    Returns a dict or None:
    {
        "playlist":  <playlist object>,
        "added_at":  "2024-03-15T12:00:00Z",   # ISO 8601
        "track":     <track object or None>,
    }
    """
    try:
        result = sp.user_playlists(user_id, limit=50)
        playlists = [p for p in (result.get("items") or []) if p]
    except Exception:
        return None

    best = None  # will hold the winning (playlist, added_at, track) tuple

    for playlist in playlists[:max_playlists]:
        total = (playlist.get("tracks") or {}).get("total", 0)
        if total == 0:
            continue

        # Fetch the last up-to-50 tracks (most likely to contain recent additions)
        offset = max(0, total - 50)
        try:
            tracks_result = sp.playlist_tracks(
                playlist["id"],
                limit=50,
                offset=offset,
                fields="items(added_at,track(id,name,artists(name),album(images,name)))",
            )
            items = [
                i for i in (tracks_result.get("items") or [])
                if i and i.get("added_at") and i.get("track")
            ]
        except Exception:
            continue

        if not items:
            continue

        latest_item = max(items, key=lambda i: i["added_at"])
        if best is None or latest_item["added_at"] > best["added_at"]:
            best = {
                "playlist": playlist,
                "added_at": latest_item["added_at"],
                "track": latest_item["track"],
            }

    return best


def get_top_recent_tracks_for_user(sp, user_id, top_n=10, max_playlists=20):
    """
    Fetches the top N most recently added tracks across all public playlists
    for a given user. Scans the last 50 tracks in each playlist (most likely
    to contain recent additions) and returns results sorted by added_at desc.

    Each returned dict:
    {
        "added_at":       "2024-03-15T12:00:00Z",
        "track":          <track object>,
        "playlist_name":  str,
        "playlist_url":   str,
        "playlist_cover": str or None,
        "playlist_id":    str,
    }
    """
    try:
        result = sp.user_playlists(user_id, limit=50)
        playlists = [p for p in (result.get("items") or []) if p]
    except Exception:
        return []

    all_items = []

    for playlist in playlists[:max_playlists]:
        total = (playlist.get("tracks") or {}).get("total", 0)
        if total == 0:
            continue

        offset = max(0, total - 50)
        try:
            tracks_result = sp.playlist_tracks(
                playlist["id"],
                limit=50,
                offset=offset,
                fields="items(added_at,track(id,name,artists(name),album(images,name)))",
            )
            items = [
                i for i in (tracks_result.get("items") or [])
                if i and i.get("added_at") and i.get("track")
            ]
        except Exception:
            continue

        covers = playlist.get("images") or []
        playlist_cover = covers[0]["url"] if covers else None

        for item in items:
            all_items.append({
                "added_at": item["added_at"],
                "track": item["track"],
                "playlist_name": playlist["name"],
                "playlist_url": (playlist.get("external_urls") or {}).get("spotify", "#"),
                "playlist_cover": playlist_cover,
                "playlist_id": playlist["id"],
            })

    all_items.sort(key=lambda i: i["added_at"], reverse=True)
    return all_items[:top_n]


def get_my_followed_playlists(sp, current_user_id, max_playlists=20):
    """
    Returns the most recently updated playlists that the current user follows
    (i.e. owned by someone else), sorted by most recently added track.

    Each entry:
    {
        "playlist_id":   str,
        "playlist_name": str,
        "playlist_url":  str,
        "playlist_cover": str or None,
        "owner_name":    str,
        "owner_id":      str,
        "added_at":      "2024-03-15T12:00:00Z",
        "track":         <track dict or None>,
        "total_tracks":  int,
    }
    """
    try:
        result = sp.current_user_playlists(limit=50)
        all_playlists = []
        while result:
            all_playlists.extend(result.get("items") or [])
            if result.get("next"):
                result = sp.next(result)
            else:
                break
    except Exception:
        return []

    # Only playlists owned by someone else (i.e. followed, not created)
    followed = [
        p for p in all_playlists
        if p and (p.get("owner") or {}).get("id") != current_user_id
    ]

    entries = []
    for playlist in followed[:max_playlists]:
        total = (playlist.get("tracks") or {}).get("total", 0)
        if total == 0:
            continue

        offset = max(0, total - 50)
        try:
            tracks_result = sp.playlist_tracks(
                playlist["id"],
                limit=50,
                offset=offset,
                fields="items(added_at,track(id,name,artists(name),album(images,name)))",
            )
            items = [
                i for i in (tracks_result.get("items") or [])
                if i and i.get("added_at") and i.get("track")
            ]
        except Exception:
            continue

        if not items:
            continue

        latest = max(items, key=lambda i: i["added_at"])
        covers = playlist.get("images") or []

        entries.append({
            "playlist_id":   playlist["id"],
            "playlist_name": playlist["name"],
            "playlist_url":  (playlist.get("external_urls") or {}).get("spotify", "#"),
            "playlist_cover": covers[0]["url"] if covers else None,
            "owner_name":    (playlist.get("owner") or {}).get("display_name") or "Unknown",
            "owner_id":      (playlist.get("owner") or {}).get("id", ""),
            "added_at":      latest["added_at"],
            "track":         latest["track"],
            "total_tracks":  total,
        })

    entries.sort(key=lambda e: e["added_at"], reverse=True)
    return entries


def build_dashboard_entries(sp, friend_ids):
    """
    Given a list of Spotify user IDs (friends), fetches the most recently
    updated public playlist for each and returns a list sorted newest-first.

    Each entry:
    {
        "user_id":    str,
        "display_name": str,
        "avatar_url": str or None,
        "playlist":   <playlist dict>,
        "added_at":   "2024-03-15T12:00:00Z",
        "track":      <track dict or None>,
    }
    """
    entries = []
    for uid in friend_ids:
        try:
            profile = sp.user(uid)
        except Exception:
            continue

        update = get_latest_update_for_user(sp, uid)
        if not update:
            continue

        images = profile.get("images") or []
        avatar_url = images[0]["url"] if images else None

        entries.append({
            "user_id": uid,
            "display_name": profile.get("display_name") or uid,
            "avatar_url": avatar_url,
            "external_url": (profile.get("external_urls") or {}).get("spotify", "#"),
            "playlist": update["playlist"],
            "added_at": update["added_at"],
            "track": update["track"],
        })

    # Sort by most recently updated
    entries.sort(key=lambda e: e["added_at"], reverse=True)
    return entries

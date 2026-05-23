import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .spotify_client import (
    get_auth_manager,
    get_spotify_client,
    get_followed_artists,
    build_dashboard_entries,
    get_top_recent_tracks_for_user,
    get_my_followed_playlists,
)
from . import friends_store


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

def index(request):
    """Root URL — redirect to dashboard if logged in, else to login."""
    if request.session.get("spotify_token_info"):
        return redirect("dashboard")
    return redirect("login")


def login_view(request):
    """Landing page — shows the 'Connect with Spotify' button."""
    if request.session.get("spotify_token_info"):
        return redirect("dashboard")
    return render(request, "dashboard/login.html")


def spotify_auth_view(request):
    """Kicks off the Spotify OAuth flow (called when the user clicks the button)."""
    auth_manager = get_auth_manager(request)
    auth_url = auth_manager.get_authorize_url()
    return redirect(auth_url)


def callback_view(request):
    error = request.GET.get("error")
    if error:
        return redirect("login")

    code = request.GET.get("code")
    if not code:
        return redirect("login")

    auth_manager = get_auth_manager(request)
    # Exchanging the code saves the token to the session via our CacheHandler
    auth_manager.get_access_token(code)
    return redirect("dashboard")


def logout_view(request):
    request.session.flush()
    return redirect("login")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard_view(request):
    sp = get_spotify_client(request)
    if not sp:
        # Flush the stale session token so the login page triggers a clean re-auth
        # (handles scope upgrades like adding playlist-read-private)
        request.session.flush()
        return redirect("login")

    current_user = sp.current_user()

    # One-time migration: if friends used to live in the session, port them
    # to disk on first dashboard load after this change.
    session_friends = request.session.get("friend_ids")
    if session_friends and not friends_store.load_friends():
        for uid in session_friends:
            if isinstance(uid, str) and uid:
                friends_store.add_friend(uid)
        request.session.pop("friend_ids", None)
        request.session.modified = True

    # Friends list now lives in friends.json on disk
    friend_ids = friends_store.load_friends()

    # Fetch followed artists so the user can easily add them
    followed_artists = []
    try:
        followed_artists = get_followed_artists(sp)
    except Exception:
        pass

    # Build the sorted feed of recent playlist updates
    entries = []
    error_message = None
    if friend_ids:
        try:
            entries = build_dashboard_entries(sp, friend_ids)
        except Exception as exc:
            error_message = f"Error fetching updates: {exc}"

    # Build a uid → {display_name, avatar_url, external_url} lookup for the sidebar,
    # sourced from entries (no extra API calls needed).
    friend_info = {e["user_id"]: e for e in entries}

    # Pop any flash from the last bulk-add so we can render a banner once.
    bulk_result = request.session.pop("bulk_result", None)

    return render(request, "dashboard/dashboard.html", {
        "current_user": current_user,
        "friend_ids": friend_ids,
        "friend_info": friend_info,
        "entries": entries,
        "followed_artists": followed_artists,
        "error_message": error_message,
        "bulk_result": bulk_result,
    })


# ---------------------------------------------------------------------------
# Friend management
# ---------------------------------------------------------------------------

@require_POST
def add_friend(request):
    sp = get_spotify_client(request)
    if not sp:
        return redirect("login")

    uid = friends_store.parse_user_id(request.POST.get("user_id", ""))
    if not uid:
        return redirect("dashboard")

    # Validate that the user actually exists before adding
    try:
        sp.user(uid)
    except Exception:
        return redirect("dashboard")  # silently ignore invalid IDs

    friends_store.add_friend(uid)
    return redirect("dashboard")


@require_POST
def add_friends_bulk(request):
    """
    Accepts a textarea where each line is a Spotify user ID or profile URL.
    Each line is parsed, validated against Spotify, then persisted.
    A summary of added/duplicate/invalid counts is flashed for the next render.
    """
    sp = get_spotify_client(request)
    if not sp:
        return redirect("login")

    raw = request.POST.get("user_ids", "")
    lines = [ln for ln in raw.splitlines() if ln.strip()]

    existing = set(friends_store.load_friends())
    added = []
    duplicates = []
    invalid = []

    # De-dupe within the paste itself before hitting the API
    seen_in_input = set()

    for line in lines:
        uid = friends_store.parse_user_id(line)
        if not uid:
            invalid.append(line.strip())
            continue
        if uid in seen_in_input:
            continue  # same ID pasted twice — quiet skip
        seen_in_input.add(uid)

        if uid in existing:
            duplicates.append(uid)
            continue

        try:
            sp.user(uid)
        except Exception:
            invalid.append(uid)
            continue

        friends_store.add_friend(uid)
        existing.add(uid)
        added.append(uid)

    request.session["bulk_result"] = {
        "added": added,
        "duplicates": duplicates,
        "invalid": invalid,
    }
    request.session.modified = True
    return redirect("dashboard")


@require_POST
def remove_friend(request):
    uid = request.POST.get("user_id", "").strip()
    if uid:
        friends_store.remove_friend(uid)
    return redirect("dashboard")


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

def export_friends(request):
    """Serve the current friends list as a downloadable friends.json file."""
    if not get_spotify_client(request):
        return redirect("login")

    friends = friends_store.load_friends()
    payload = json.dumps({"friends": friends}, indent=2)
    response = HttpResponse(payload, content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="friends.json"'
    return response


@require_POST
def import_friends(request):
    """
    Accept a JSON file upload containing a friends list.
    Supports two formats:
      - {"friends": ["id1", "id2", ...]}   (export format)
      - ["id1", "id2", ...]                 (plain list)

    If the 'replace' checkbox is checked, the existing list is cleared first.
    IDs are NOT validated against the Spotify API (assumed trusted from a prior
    export); invalid IDs will simply not show up in the feed.
    """
    sp = get_spotify_client(request)
    if not sp:
        return redirect("login")

    uploaded = request.FILES.get("friends_file")
    if not uploaded:
        return redirect("dashboard")

    try:
        data = json.load(uploaded)
    except (json.JSONDecodeError, Exception):
        request.session["bulk_result"] = {
            "added": [],
            "duplicates": [],
            "invalid": ["Could not parse file — make sure it is valid JSON."],
        }
        request.session.modified = True
        return redirect("dashboard")

    # Normalise to a flat list of raw strings
    if isinstance(data, list):
        raw_ids = data
    elif isinstance(data, dict) and "friends" in data:
        raw_ids = data["friends"]
    else:
        request.session["bulk_result"] = {
            "added": [],
            "duplicates": [],
            "invalid": ['Unexpected format — expected {"friends": [...]} or a plain list.'],
        }
        request.session.modified = True
        return redirect("dashboard")

    replace = request.POST.get("replace") == "on"
    if replace:
        friends_store.save_friends([])

    existing = set(friends_store.load_friends())
    added = []
    duplicates = []

    for item in raw_ids:
        if not isinstance(item, str):
            continue
        uid = friends_store.parse_user_id(item)
        if not uid:
            continue
        if uid in existing:
            duplicates.append(uid)
            continue
        friends_store.add_friend(uid)
        existing.add(uid)
        added.append(uid)

    request.session["bulk_result"] = {
        "added": added,
        "duplicates": duplicates,
        "invalid": [],
    }
    request.session.modified = True
    return redirect("dashboard")


# ---------------------------------------------------------------------------
# My followed playlists (JSON — lazy loaded by the Following tab)
# ---------------------------------------------------------------------------

def my_following_view(request):
    """
    Returns JSON with the current user's followed playlists (owned by others)
    sorted by most recently added track.

    Response shape:
    {
        "playlists": [ { "playlist_id", "playlist_name", "playlist_url",
                         "playlist_cover", "owner_name", "owner_id",
                         "added_at", "track", "total_tracks" }, ... ]
    }
    """
    sp = get_spotify_client(request)
    if not sp:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    current_user = sp.current_user()
    current_user_id = current_user["id"]

    playlists = get_my_followed_playlists(sp, current_user_id)
    return JsonResponse({"playlists": playlists})


# ---------------------------------------------------------------------------
# Friend detail — top recent tracks (JSON)
# ---------------------------------------------------------------------------

def friend_tracks_view(request, user_id):
    """
    Returns JSON with a user's profile and their top 10 most recently added
    tracks across all public playlists.

    Response shape:
    {
        "user":   { "id", "display_name", "avatar_url", "external_url" },
        "tracks": [ { "added_at", "track", "playlist_name",
                      "playlist_url", "playlist_cover", "playlist_id" }, ... ]
    }
    """
    sp = get_spotify_client(request)
    if not sp:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    try:
        profile = sp.user(user_id)
    except Exception:
        return JsonResponse({"error": "User not found"}, status=404)

    images = profile.get("images") or []
    avatar_url = images[0]["url"] if images else None

    tracks = get_top_recent_tracks_for_user(sp, user_id)

    return JsonResponse({
        "user": {
            "id": user_id,
            "display_name": profile.get("display_name") or user_id,
            "avatar_url": avatar_url,
            "external_url": (profile.get("external_urls") or {}).get("spotify", "#"),
        },
        "tracks": tracks,
    })

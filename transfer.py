#!/usr/bin/env python3
"""
YouTube Music — Liked Music to Playlist Exporter
------------------------------------------------
Clones or syncs the YouTube Music 'Liked Music' auto-playlist into a standard
user playlist using ytmusicapi.

Features:
- Parses 'Copy as cURL (bash)', 'Copy as cURL (cmd)', or raw Request Headers
  from headers.txt (bypasses the Windows 4,095-character terminal paste limit).
- Validates the SAPISID authentication cookie before making API calls.
- Supports creating a new playlist or resuming/syncing into an existing one.
- Uses a recursive Binary Search Tree (divide-and-conquer) batch insertion
  algorithm to bypass YouTube's all-or-nothing batch failure behavior and
  isolate individual corrupted/unavailable tracks.
- Exports a detailed report of troubled and duplicate tracks to failed_tracks.txt.
"""

import os
import re
import sys
import time
import json
import traceback
from datetime import datetime

try:
    import ytmusicapi
    from ytmusicapi import YTMusic
except ImportError:
    print("ERROR: 'ytmusicapi' is not installed.")
    print("Run: pip install ytmusicapi")
    input("\nPress Enter to exit...")
    sys.exit(1)


# ==============================================================================
# CONFIGURATION DEFAULTS
# ==============================================================================
DEFAULT_PLAYLIST_TITLE = "Liked Music Archive"
DEFAULT_PLAYLIST_DESC = "Cloned from Liked Music via yt-music-sync"
DEFAULT_PRIVACY = "PRIVATE"  # Options: PRIVATE, PUBLIC, UNLISTED
INITIAL_BATCH_SIZE = 200     # Starting chunk size before tree splitting
SPLIT_DELAY_SECONDS = 0.5    # Rate-limit buffer during recursive splits


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def extract_headers_from_text(raw_text: str) -> str:
    """
    Converts 'Copy as cURL (bash)', 'Copy as cURL (cmd)', or raw HTTP headers
    into clean 'Header: Value' lines compatible with ytmusicapi.setup().
    """
    raw_text = raw_text.strip()

    if raw_text.startswith("curl "):
        # Normalize Windows cURL caret (^) line continuations and escaped quotes
        normalized = re.sub(r"\^\r?\n", " ", raw_text)
        normalized = normalized.replace('^"', '"').replace("^%", "%").replace("^^", "^")

        headers = []
        # Match -H '...' or -H "..." or --header '...'
        pattern = r"(?:-H|--header)\s+(?:'([^']*)'|\"([^\"]*)\")"
        for match in re.finditer(pattern, normalized):
            line = match.group(1) or match.group(2)
            # Skip HTTP/2 pseudo-headers (:authority, :method, :path, :scheme)
            if line and not line.startswith(":"):
                headers.append(line)

        # Match -b '...' or --cookie '...' (Chromium 123+ moves cookies to -b flag)
        cookie_pattern = r"(?:-b|--cookie)\s+(?:'([^']*)'|\"([^\"]*)\")"
        cookie_match = re.search(cookie_pattern, normalized)
        if cookie_match:
            cookie_val = cookie_match.group(1) or cookie_match.group(2)
            headers.append(f"cookie: {cookie_val}")

        return "\n".join(headers)

    return raw_text


def setup_authentication(script_dir: str) -> str | None:
    """
    Verifies or generates browser.json from headers.txt and checks for SAPISID.
    Returns the path to browser.json if valid, or None on failure.
    """
    auth_file = os.path.join(script_dir, "browser.json")
    raw_headers_file = os.path.join(script_dir, "headers.txt")

    if os.path.exists(raw_headers_file):
        print("[*] Found 'headers.txt'. Parsing and building 'browser.json'...")
        with open(raw_headers_file, "r", encoding="utf-8") as f:
            raw_content = f.read()

        if raw_content.strip():
            cleaned_headers = extract_headers_from_text(raw_content)
            if "SAPISID" not in cleaned_headers:
                print("\n[!] ERROR: 'headers.txt' is missing the 'SAPISID' login cookie.")
                print("    1. Log into https://music.youtube.com")
                print("    2. Open DevTools (F12) -> Network tab -> Filter by '/browse'")
                print("    3. Click 'Library' in YouTube Music to trigger 'browse?prettyPrint=false'")
                print("    4. Right-click it -> Copy -> Copy as cURL (bash)")
                print("    5. Paste the result into 'headers.txt' and save.")
                return None

            ytmusicapi.setup(filepath=auth_file, headers_raw=cleaned_headers)
            print(f"[+] Successfully generated 'browser.json' ({os.path.getsize(auth_file)} bytes).")

    if not os.path.exists(auth_file):
        print("\n[!] ERROR: Authentication file not found!")
        print(f"    Create a file named 'headers.txt' in:\n    {script_dir}")
        print("    Paste your 'Copy as cURL (bash)' output from music.youtube.com into it, then re-run.")
        return None

    # Validate existing browser.json
    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
        cookie_str = auth_data.get("cookie", "") or auth_data.get("Cookie", "")
        if "SAPISID" not in cookie_str:
            print("\n[!] ERROR: 'browser.json' is missing the 'SAPISID' session cookie.")
            print("    Your terminal likely truncated the paste. Use 'headers.txt' instead.")
            return None
    except Exception as e:
        print(f"\n[!] ERROR: Failed to parse 'browser.json': {e}")
        return None

    return auth_file


def format_track_info(track: dict) -> str:
    """Formats a track dictionary into a clean 'Title - Artist (URL)' string."""
    title = track.get("title", "Unknown Title")
    artists_list = [a.get("name", "") for a in track.get("artists", []) if a.get("name")]
    artists = ", ".join(artists_list) if artists_list else "Unknown Artist"
    vid = track.get("videoId", "Unknown_ID")
    return f"{title} — {artists} (https://music.youtube.com/watch?v={vid})"


def add_tracks_tree(yt: YTMusic, playlist_id: str, chunk: list, failed_list: list, depth: int = 0) -> int:
    """
    Recursively inserts a batch of tracks into a playlist.
    If YouTube rejects a batch (STATUS_FAILED), splits the batch in half like a
    binary search tree until every valid track is added and exact broken tracks
    are isolated at depth leaf (len == 1).
    """
    if not chunk:
        return 0

    indent = "  " * depth
    video_ids = [t["videoId"] for t in chunk]

    try:
        res = yt.add_playlist_items(playlist_id, video_ids, duplicates=True)
        status = res.get("status", "") if isinstance(res, dict) else str(res)
    except Exception as e:
        status = f"EXCEPTION ({e})"

    if "SUCCEEDED" in status:
        print(f"{indent}[OK] Added batch of {len(chunk)} tracks.")
        return len(chunk)

    # Base case: single track failed -> isolate and record it
    if len(chunk) == 1:
        bad_track = chunk[0]
        info = format_track_info(bad_track)
        print(f"{indent}[!] ISOLATED TROUBLED TRACK: {info}")
        failed_list.append(bad_track)
        return 0

    # Recursive step: split failed chunk in half
    mid = len(chunk) // 2
    left_half = chunk[:mid]
    right_half = chunk[mid:]

    print(f"{indent}[~] Batch of {len(chunk)} failed ({status}). Splitting into {len(left_half)} + {len(right_half)}...")
    time.sleep(SPLIT_DELAY_SECONDS)

    added_left = add_tracks_tree(yt, playlist_id, left_half, failed_list, depth + 1)
    added_right = add_tracks_tree(yt, playlist_id, right_half, failed_list, depth + 1)
    return added_left + added_right


# ==============================================================================
# MAIN WORKFLOW
# ==============================================================================
def main():
    print("=" * 65)
    print("   YouTube Music — Liked Music to Playlist Exporter & Sync")
    print("=" * 65)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    failed_log_path = os.path.join(script_dir, "failed_tracks.txt")

    # 1. Setup & Verify Auth
    auth_file = setup_authentication(script_dir)
    if not auth_file:
        return

    yt = YTMusic(auth_file)

    # 2. Fetch Liked Music
    print("\n[1/4] Fetching 'Liked Music' library (this may take a moment)...")
    try:
        liked_data = yt.get_liked_songs(limit=None)
    except Exception as e:
        print(f"\n[!] Failed to fetch Liked Music. Your session may have expired.\n    Details: {e}")
        return

    raw_tracks = liked_data.get("tracks", [])
    valid_liked = [t for t in raw_tracks if t.get("videoId")]
    print(f"      Found {len(valid_liked)} tracks with valid video IDs (out of {len(raw_tracks)} total items).")

    if not valid_liked:
        print("\n[!] No liked tracks found on this profile.")
        print("    If you use a Brand Account, check 'x-goog-authuser' in your headers.")
        return

    # 3. Choose Target Playlist (Create New vs. Resume/Sync Existing)
    print("\n[2/4] Select Target Playlist:")
    print("      Press [ENTER] to create a new playlist, OR")
    print("      Paste an existing Playlist ID (e.g., PLQnc9...) to sync/resume missing tracks.")
    user_choice = input("      Your choice: ").strip()

    existing_ids = set()
    if user_choice:
        # Clean full URL if user pasted a full YouTube Music link
        if "list=" in user_choice:
            user_choice = user_choice.split("list=")[-1].split("&")[0]
        playlist_id = user_choice
        print(f"\n[*] Fetching existing tracks from playlist '{playlist_id}'...")
        try:
            existing_pl = yt.get_playlist(playlist_id, limit=None)
            existing_ids = {t.get("videoId") for t in existing_pl.get("tracks", []) if t.get("videoId")}
            print(f"    Found {len(existing_ids)} unique tracks already in '{existing_pl.get('title', playlist_id)}'.")
        except Exception as e:
            print(f"\n[!] Could not load playlist '{playlist_id}': {e}")
            return
    else:
        custom_title = input(f"      Enter new playlist title (default: '{DEFAULT_PLAYLIST_TITLE}'): ").strip()
        title = custom_title if custom_title else DEFAULT_PLAYLIST_TITLE
        print(f"\n[*] Creating new {DEFAULT_PRIVACY.lower()} playlist '{title}'...")
        playlist_id = yt.create_playlist(
            title=title,
            description=DEFAULT_PLAYLIST_DESC,
            privacy_status=DEFAULT_PRIVACY
        )
        if isinstance(playlist_id, dict) or not playlist_id:
            print(f"\n[!] Failed to create playlist. API Response:\n{json.dumps(playlist_id, indent=2)}")
            return
        print(f"    Created Playlist ID: {playlist_id}")

    # 4. Filter Missing & Duplicate Tracks
    tracks_to_add = []
    duplicate_tracks = []
    seen_in_source = set()

    for t in valid_liked:
        vid = t["videoId"]
        if vid in seen_in_source:
            duplicate_tracks.append(t)
            continue
        seen_in_source.add(vid)

        if vid not in existing_ids:
            tracks_to_add.append(t)

    print(f"\n[3/4] Queue Summary:")
    print(f"      - Unique Liked Tracks : {len(seen_in_source)}")
    print(f"      - Duplicate IDs       : {len(duplicate_tracks)}")
    print(f"      - Already in Playlist : {len(existing_ids)}")
    print(f"      - Tracks to Transfer  : {len(tracks_to_add)}")

    if not tracks_to_add:
        print("\n[+] All valid tracks are already present in the target playlist!")
        print(f"    Playlist URL: https://music.youtube.com/playlist?list={playlist_id}")
        return

    # 5. Execute Transfer with Binary Tree Fallback
    print(f"\n[4/4] Transferring {len(tracks_to_add)} tracks (Batch size: {INITIAL_BATCH_SIZE}, Tree-Split enabled)...")
    failed_tracks = []
    total_added = 0

    for i in range(0, len(tracks_to_add), INITIAL_BATCH_SIZE):
        batch = tracks_to_add[i : i + INITIAL_BATCH_SIZE]
        end_idx = i + len(batch)
        print(f"\n--- Batch {i + 1} to {end_idx} (of {len(tracks_to_add)}) ---")
        total_added += add_tracks_tree(yt, playlist_id, batch, failed_tracks)

    # 6. Summary & Log Export
    print("\n" + "=" * 65)
    print("   TRANSFER SUMMARY")
    print("=" * 65)
    print(f"  Successfully Added   : {total_added} / {len(tracks_to_add)} tracks")
    print(f"  Isolated Bad Tracks  : {len(failed_tracks)}")
    print(f"  Duplicate Tracks     : {len(duplicate_tracks)}")
    print(f"  Playlist Direct URL  : https://music.youtube.com/playlist?list={playlist_id}")
    print("=" * 65)

    if failed_tracks or duplicate_tracks:
        with open(failed_log_path, "w", encoding="utf-8") as f:
            f.write(f"YouTube Music Sync Report — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Target Playlist: https://music.youtube.com/playlist?list={playlist_id}\n")
            f.write("=" * 75 + "\n\n")

            f.write(f"=== ISOLATED TROUBLED TRACKS ({len(failed_tracks)}) ===\n")
            f.write("These tracks were rejected by the YouTube Music API (unavailable, region-locked, or restricted):\n\n")
            if failed_tracks:
                for idx, t in enumerate(failed_tracks, 1):
                    line = f"{idx}. {format_track_info(t)}"
                    f.write(line + "\n")
            else:
                f.write("None!\n")

            f.write(f"\n=== DUPLICATE VIDEO IDs IN LIKED MUSIC ({len(duplicate_tracks)}) ===\n")
            f.write("These tracks appeared more than once in your Liked Music list:\n\n")
            if duplicate_tracks:
                for idx, t in enumerate(duplicate_tracks, 1):
                    f.write(f"{idx}. {format_track_info(t)}\n")
            else:
                f.write("None!\n")

        print(f"\n[*] Detailed log saved to:\n    {failed_log_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Operation cancelled by user.")
    except BaseException:
        print("\n--- UNEXPECTED CRASH / ERROR DETAILS ---")
        traceback.print_exc()
    finally:
        input("\nPress Enter to exit...")
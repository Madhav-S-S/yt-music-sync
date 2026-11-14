\# YouTube Music — Liked Music Exporter \& Sync (`yt-music-sync`)



A Python utility to clone, archive, or sync your YouTube Music \*\*Liked Music\*\* auto-playlist into a standard user playlist using \[`ytmusicapi`](https://github.com/sigma67/ytmusicapi).



\## Why This Exists



1\. \*\*Bypasses Browser Lazy-Loading:\*\* YouTube Music's web interface lazy-loads tracks as you scroll, making it nearly impossible to manually select and copy thousands of songs at once.

2\. \*\*Fixes the Windows 4,095-Character Terminal Limit:\*\* Pasting large browser cookies directly into the Windows terminal via `ytmusicapi browser` silently truncates the `SAPISID` session cookie. This script parses \*\*Copy as cURL (bash)\*\* or raw headers directly from a local `headers.txt` file.

3\. \*\*Binary-Tree Batch Recovery:\*\* YouTube Music's API uses all-or-nothing batch transactions—if a single song in a 200-track batch is region-locked, deleted, or restricted, the entire batch of 200 fails with `STATUS\_FAILED`. When a batch fails, this script automatically splits it in half recursively (like a binary search tree) until every valid song is added and the exact broken tracks are isolated.



\---



\## Features



\* \*\*Zero-Truncation Auth:\*\* Automatically extracts headers and cookies from `Copy as cURL (bash)`, `Copy as cURL (cmd)`, or raw HTTP headers.

\* \*\*Create or Resume/Sync:\*\* Create a brand-new playlist or paste an existing Playlist ID/URL to sync only missing songs.

\* \*\*Divide-and-Conquer Insertion:\*\* Recursively splits failed chunks down to single tracks so one bad song never drops an entire batch.

\* \*\*Detailed Troubled Track Logging:\*\* Exports a clean list of rejected/unavailable songs and duplicate video IDs with direct links to `failed\_tracks.txt`.



\---



\## Prerequisites



Make sure you have \*\*Python 3.10+\*\* installed, then install `ytmusicapi`:



```bash

pip install ytmusicapi

```



\---



\## How to Use



\### Step 1: Grab Your YouTube Music Session Headers

1\. Open \[music.youtube.com](https://music.youtube.com) in your browser (Brave, Chrome, Edge, or Firefox) and make sure you are signed in.

2\. Press \*\*F12\*\* (or `Ctrl + Shift + I`) to open \*\*Developer Tools\*\* and switch to the \*\*Network\*\* tab.

3\. Type `/browse` into the filter box.

4\. Click \*\*Library\*\* on the YouTube Music page to trigger a `POST` request named `browse?prettyPrint=false` (Status `200`).

5\. \*\*Right-click\*\* on `browse?prettyPrint=false` → \*\*Copy\*\* → \*\*Copy as cURL (bash)\*\*.

6\. Create a new file named \*\*`headers.txt`\*\* in the same folder as `transfer.py`, paste the copied cURL command inside, and save it.



\### Step 2: Run the Script

```bash

python transfer.py

```

\*(On Windows, you can also double-click `transfer.py` directly.)\*



\### Step 3: Choose Your Mode

When prompted in the terminal:

\* Press \*\*Enter\*\* to create a brand-new playlist (default title: `Liked Music Archive`).

\* \*\*Or\*\* paste an existing Playlist ID / URL to sync only the tracks that aren't already in that playlist.



\---



\## How the Binary-Tree Recovery Works



```text

Batch of 200 tracks -> STATUS\_FAILED

&#x20;├── Split Left (100 tracks)  -> STATUS\_SUCCEEDED (100 added)

&#x20;└── Split Right (100 tracks) -> STATUS\_FAILED

&#x20;     ├── Split Left (50 tracks)  -> STATUS\_SUCCEEDED (50 added)

&#x20;     └── Split Right (50 tracks) -> Splits down to 1 track -> \[!] ISOLATED TROUBLED TRACK

```



Any track that fails at depth `1` is logged to \*\*`failed\_tracks.txt`\*\* with its title, artist, and direct YouTube Music URL so you can review or replace it manually.



\---



\## Security Note



\*\*Never commit or share your `browser.json` or `headers.txt` files.\*\*  

They contain your active Google account session cookies (`SAPISID`). Anyone with those files can access your YouTube account without your password. Delete both files once your transfer is complete.



\---



\## License



MIT License


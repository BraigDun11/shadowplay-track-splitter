# -*- coding: utf-8 -*-
"""Self-update from GitHub releases.

Two channels:
  * stable (default): only release versions with two numbers - 1.4, 1.5, 1.6 ...
  * developer: every release - 1.4.10, 1.4.11, 1.5, 1.5.1 ...
The new exe is downloaded next to the running one, the running exe is renamed to *.old
(Windows allows renaming a running program), the new one takes its place and is started.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = "BraigDun11/shadowplay-track-splitter"
API = "https://api.github.com/repos/%s/releases?per_page=40" % REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % REPO
PAGE = "https://github.com/%s/releases" % REPO
UA = "ShadowPlayTrackSplitter-updater"


def parse_version(tag):
    """'v1.4.10' -> (1, 4, 10); None if it is not a version."""
    m = re.fullmatch(r"[vV]?(\d+(?:\.\d+){1,3})", (tag or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def is_stable(ver):
    return ver is not None and len(ver) == 2


def pick_update(releases, current, dev=False):
    """The newest suitable release that is newer than `current`, or None.
    Returns {'tag', 'version', 'url', 'size', 'sha256', 'page'}."""
    cur = parse_version(current)
    best = None
    for r in releases or []:
        if r.get("draft"):
            continue
        ver = parse_version(r.get("tag_name"))
        if ver is None or (not dev and not is_stable(ver)):
            continue
        if cur is not None and ver <= cur:
            continue
        asset = None
        for a in r.get("assets") or []:
            if str(a.get("name", "")).lower().endswith(".exe"):
                asset = a
                break
        if asset is None:
            continue
        url = asset.get("browser_download_url") or ""
        if not url.startswith(DOWNLOAD_PREFIX):
            continue
        if best is None or ver > best["version"]:
            dg = str(asset.get("digest") or "")
            best = {"tag": r["tag_name"], "version": ver, "url": url, "size": int(asset.get("size") or 0),
                    "sha256": dg.split(":", 1)[1].lower() if dg.lower().startswith("sha256:") else None,
                    "page": r.get("html_url") or PAGE}
    return best


def fetch_releases(timeout=8):
    req = urllib.request.Request(API, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check(current, dev=False, timeout=8):
    """Returns (update_or_None, error_text_or_None)."""
    try:
        return pick_update(fetch_releases(timeout), current, dev), None
    except Exception as ex:     # offline, rate limit, ...
        return None, str(ex)


def download(url, dest, progress=None, size=0, sha256=None, cancelled=None):
    """Download to dest (a partial file is removed on failure)."""
    if not url.startswith(DOWNLOAD_PREFIX):
        raise ValueError("unexpected download address")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    h = hashlib.sha256()
    got = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or size or 0)
            while True:
                if cancelled and cancelled():
                    raise RuntimeError("cancelled")
                chunk = r.read(1 << 18)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress and total:
                    progress(min(1.0, got / total))
        if size and got != size:
            raise IOError("incomplete download")
        if sha256 and h.hexdigest().lower() != sha256:
            raise IOError("checksum mismatch")
        with open(dest, "rb") as f:
            if f.read(2) != b"MZ":
                raise IOError("not an executable")
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise


def can_self_update():
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def apply_update(new_path, exe=None):
    """Swap the running exe for the downloaded one and start it. Raises OSError when it cannot."""
    exe = exe or sys.executable
    old = exe + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass
    os.replace(exe, old)
    try:
        os.replace(new_path, exe)
    except OSError:
        os.replace(old, exe)            # put everything back
        raise
    return exe


def start(exe):
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe], close_fds=True, creationflags=flags)


def cleanup_old():
    """Remove the leftovers of the previous update (called at start-up)."""
    if getattr(sys, "frozen", False):
        try:
            p = sys.executable + ".old"
            if os.path.exists(p):
                os.remove(p)
            p = sys.executable + ".new"
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass

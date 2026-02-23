import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
# Project root = directory that contains "data" and "images" (same base for all paths)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SMASHI_FILE = os.path.join(DATA_DIR, "podcasts_smashi.json")
LOVIN_FILE = os.path.join(DATA_DIR, "podcasts_lovin.json")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _flatten_podcasts(raw_list):
    """Handle both [{}] and [[{}, {}]] structures."""
    out = []
    for item in raw_list:
        if isinstance(item, list):
            out.extend(item)
        else:
            out.append(item)
    return out


def _load_smashi():
    data = _load_json(SMASHI_FILE)
    return _flatten_podcasts(data["podcasts"])


def _load_lovin():
    data = _load_json(LOVIN_FILE)
    return _flatten_podcasts(data["podcasts"])


# Load once globally (fast lookups)
SMASHI_PODCASTS = _load_smashi()
LOVIN_PODCASTS = _load_lovin()
SMASHI_INDEX = {p["podcast_id"]: p for p in SMASHI_PODCASTS}
LOVIN_INDEX = {p["podcast_id"]: p for p in LOVIN_PODCASTS}
LOVIN_IDS = set(LOVIN_INDEX.keys())


def find_cms_show_id(podcast_id: int):
    """
    Returns cms_show_id for a given podcast_id (from Smashi list).
    Returns None if not found.
    """
    podcast = SMASHI_INDEX.get(podcast_id)
    return podcast["cms_show_id"] if podcast else None


def find_cms_category_id(podcast_id: int):
    """
    Returns cms_category_id for a given podcast_id (from Smashi list).
    Returns None if not found.
    """
    podcast = SMASHI_INDEX.get(podcast_id)
    return podcast["cms_category_id"] if podcast else None

def find_lovin_show_id(podcast_id : int):
    podcast = LOVIN_INDEX.get(podcast_id)
    return podcast["cms_show_id"] if podcast else None

def find_lovin_category_id(podcast_id : int):
    podcast = LOVIN_INDEX.get(podcast_id)
    return podcast["cms_category_id"] if podcast else None

def _normalize_podcast_id(podcast_id):
    """Convert to int for index lookup (API often sends string)."""
    if podcast_id is None:
        return None
    try:
        return int(podcast_id)
    except (TypeError, ValueError):
        return None


def is_lovin_podcast(podcast_id) -> bool:
    """True if podcast_id is in podcasts_lovin.json. Accepts int or string."""
    pid = _normalize_podcast_id(podcast_id)
    return pid is not None and pid in LOVIN_INDEX


def is_smashi_podcast(podcast_id) -> bool:
    """True if podcast_id is in podcasts_smashi.json. Accepts int or string."""
    pid = _normalize_podcast_id(podcast_id)
    return pid is not None and pid in SMASHI_INDEX


def get_show_title(podcast_id):
    """
    Returns show_title for a given podcast_id from podcasts_lovin.json or podcasts_smashi.json.
    Returns None if not found. Accepts int or numeric string.
    """
    if podcast_id is None:
        return None
    try:
        pid = int(podcast_id)
    except (TypeError, ValueError):
        return None
    podcast = LOVIN_INDEX.get(pid) or SMASHI_INDEX.get(pid)
    return podcast.get("show_title") if podcast else None


def get_poster_image_path(podcast_id):
    """
    Returns the image_path for a given podcast_id from the podcast data (lovin or smashi).
    Path is relative to project root (e.g. "images/lovin/Lovin Cairo.jpg").
    Returns None if not found or path not set.
    """
    if podcast_id is None:
        return None
    try:
        pid = int(podcast_id)
    except (TypeError, ValueError):
        return None
    podcast = LOVIN_INDEX.get(pid) or SMASHI_INDEX.get(pid)
    if not podcast:
        return None
    path = podcast.get("image_path") or ""
    return path.strip() or None

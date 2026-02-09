import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
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

def is_lovin_podcast(podcast_id: int) -> bool:
    """True if podcast_id is in podcasts_lovin.json."""
    return podcast_id in LOVIN_INDEX


def is_smashi_podcast(podcast_id: int) -> bool:
    """True if podcast_id is in podcasts_smashi.json."""
    return podcast_id in SMASHI_INDEX

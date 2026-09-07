"""
src/ingest.py
-------------
Data ingestion, sender resolution, and chronological train/holdout splitting.
Enforces the anti-leakage contract:
- First 70% of emails by date = training (profiles & nulls).
- Last 30% of emails by date = genuine holdout (strictly for evaluation).
"""

import json
import os
from typing import Dict, List, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PREPARED_DIR = os.path.join(DATA_DIR, "prepared")
SENDERS_FILE = os.path.join(DATA_DIR, "senders.json")

# Marcus Hale demo persona mapping
DEMO_ALIAS_MAP = {
    "marcus hale": "presto-k",
    "marcus hale, cfo": "presto-k",
    "marcus hale (cfo)": "presto-k",
    "cfo": "presto-k",
}


def load_senders_catalog() -> Dict:
    """Loads the catalog of enrolled senders and their volume tiers."""
    if not os.path.exists(SENDERS_FILE):
        raise FileNotFoundError(f"Senders catalog not found at {SENDERS_FILE}")
    with open(SENDERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_sender_id(sender_identifier: str) -> Optional[str]:
    """
    Resolves a raw sender identifier (email, display name, alias, or sender_id)
    to the canonical sender_id. Returns None if unknown.
    """
    if not sender_identifier:
        return None
    
    clean = sender_identifier.strip().lower()
    if clean in DEMO_ALIAS_MAP:
        return DEMO_ALIAS_MAP[clean]

    catalog = load_senders_catalog()
    for s in catalog["senders"]:
        sid = s["sender_id"].lower()
        dname = s["display_name"].lower()
        alias = (s.get("alias") or "").lower()
        if clean == sid or clean == dname or (alias and clean == alias):
            return s["sender_id"]
        # Match email prefixes if formatted as user@enron.com
        clean_prefix = clean.split("@")[0].replace(".", "-")
        if clean_prefix == sid:
            return s["sender_id"]

    # Direct check if file exists in prepared
    direct_path = os.path.join(PREPARED_DIR, f"{clean}.jsonl")
    if os.path.exists(direct_path):
        return clean

    return None


def load_sender_emails(sender_id: str) -> List[Dict]:
    """
    Loads all cleaned emails for a sender, sorted chronologically by date.
    """
    canonical_id = resolve_sender_id(sender_id)
    if not canonical_id:
        raise ValueError(f"Unknown sender identifier: '{sender_id}'")

    file_path = os.path.join(PREPARED_DIR, f"{canonical_id}.jsonl")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Prepared data not found for sender '{canonical_id}' at {file_path}")

    emails = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                emails.append(json.loads(line))

    # Guarantee chronological order
    emails.sort(key=lambda x: x.get("date", ""))
    return emails


def split_sender_data(sender_id: str, train_ratio: float = 0.70) -> Tuple[List[Dict], List[Dict]]:
    """
    Strict chronological split:
    - First 70% of emails = training set
    - Last 30% of emails = genuine holdout set
    """
    emails = load_sender_emails(sender_id)
    if not emails:
        return [], []

    n_total = len(emails)
    n_train = int(n_total * train_ratio)
    
    # Guarantee at least 1 holdout email if possible
    if n_train == n_total and n_total > 1:
        n_train = n_total - 1

    train_set = emails[:n_train]
    holdout_set = emails[n_train:]
    return train_set, holdout_set


def get_all_senders() -> List[Dict]:
    """Returns list of sender metadata dicts from senders.json."""
    return load_senders_catalog()["senders"]

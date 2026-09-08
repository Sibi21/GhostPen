"""
src/demo_inbox.py
-----------------
Per-sender demonstration inbox builder for GhostPen.
Constructs contextual executive mailboxes with fixed deterministic sampling.
"""

import json
import os
import random
from typing import Dict, List, Optional

from src.ingest import get_all_senders, resolve_sender_id, split_sender_data

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
PINNED_DEMO_INBOX = os.path.join(DATA_DIR, "demo_inbox.json")
FORGED_FILE = os.path.join(DATA_DIR, "forged", "forged.jsonl")

# Fixed documented sampling seed
DEMO_SEED = 42


class InboxList(list):
    """
    Subclass of list with inbox metadata properties for UI and test reflection.
    """
    def __init__(
        self,
        items: List[Dict],
        genuine_only: bool = False,
        has_short_genuine: bool = False,
        sender_id: str = "",
        display_name: str = "",
        volume_class: str = "",
        note: str = "",
    ):
        super().__init__(items)
        self.genuine_only = genuine_only
        self.has_short_genuine = has_short_genuine
        self.sender_id = sender_id
        self.display_name = display_name
        self.volume_class = volume_class
        self.note = note


def _load_sender_meta(canon_id: str) -> Optional[Dict]:
    senders = get_all_senders()
    for s in senders:
        if s["sender_id"] == canon_id:
            return s
    return None


def build_inbox(sender_id: str) -> InboxList:
    """
    Builds or retrieves a deterministic demo inbox for the given sender.
    
    Rules:
    - For the aliased demo sender ("Marcus Hale" / "presto-k"), returns exactly
      the pinned ordered list from data/demo_inbox.json (same IDs, same order).
    - For high-volume senders: 8 genuine + 2 generic + 2 styled + 1 short evasion
      (+ 1 short genuine if one under 40 words exists, else 13 messages).
    - For low-volume senders: genuine holdout only (up to 8, or all if < 8).
    - Sampling is strictly deterministic via fixed DEMO_SEED.
    - Relabel tier is excluded.
    """
    # 1. Canonical Aliased Demo Sender (Marcus Hale / presto-k)
    if sender_id in ["Marcus Hale", "Marcus Hale (CFO)"] or sender_id == "presto-k":
        if os.path.exists(PINNED_DEMO_INBOX):
            with open(PINNED_DEMO_INBOX, "r", encoding="utf-8") as f:
                pinned_items = json.load(f)
            return InboxList(
                pinned_items,
                genuine_only=False,
                has_short_genuine=True,
                sender_id="presto-k",
                display_name="Marcus Hale (CFO)",
                volume_class="high",
                note="Canonical demo inbox with 14 benchmark messages.",
            )

    canon_id = resolve_sender_id(sender_id)
    if not canon_id:
        raise ValueError(f"Unknown sender identifier: {sender_id}")

    meta = _load_sender_meta(canon_id)
    if not meta:
        raise ValueError(f"Metadata not found for sender {canon_id}")

    display_name = meta["display_name"]
    volume_class = meta["volume_class"]

    train_records, holdout_records = split_sender_data(canon_id)

    # 2. Low-Volume Senders: Genuine Holdout Only
    if volume_class == "low":
        short_cands = [m for m in holdout_records if m.get("word_count", len(m["body"].split())) < 40]
        has_short = len(short_cands) > 0

        rng = random.Random(DEMO_SEED)
        sorted_holdout = sorted(holdout_records, key=lambda m: (m.get("date", ""), m.get("subject", "")))
        if len(sorted_holdout) <= 8:
            selected_records = list(sorted_holdout)
        else:
            selected_records = rng.sample(sorted_holdout, 8)
            selected_records.sort(key=lambda m: m.get("date", ""))

        inbox_items = []
        for idx, m in enumerate(selected_records):
            wc = m.get("word_count", len(m["body"].split()))
            cat = "short_genuine" if wc < 40 else "genuine_holdout"
            inbox_items.append({
                "id": f"{canon_id}_{idx+1:02d}",
                "sender": display_name,
                "subject": m.get("subject", "Operational notice"),
                "date": m.get("date", "2001-10-01")[:10],
                "body": m["body"],
                "category": cat,
            })

        note = "low-volume sender: no forged demo messages authored; see evaluation stress table."
        return InboxList(
            inbox_items,
            genuine_only=True,
            has_short_genuine=has_short,
            sender_id=canon_id,
            display_name=display_name,
            volume_class="low",
            note=note,
        )

    # 3. High-Volume Senders: 8 genuine + 2 generic + 2 styled + 1 short (+/- short genuine)
    # Check for shortest genuine under 40 words
    short_cands = [m for m in holdout_records if m.get("word_count", len(m["body"].split())) < 40]
    if short_cands:
        short_genuine_rec = min(short_cands, key=lambda m: m.get("word_count", len(m["body"].split())))
        has_short_genuine = True
    else:
        short_genuine_rec = None
        has_short_genuine = False

    # Filter out short_genuine_rec from the regular 8-message pool
    regular_pool = [
        m for m in holdout_records
        if short_genuine_rec is None or m["body"] != short_genuine_rec["body"]
    ]

    rng = random.Random(DEMO_SEED)
    sorted_regular = sorted(regular_pool, key=lambda m: (m.get("date", ""), m.get("subject", "")))
    selected_genuine = rng.sample(sorted_regular, min(8, len(sorted_regular)))
    selected_genuine.sort(key=lambda m: m.get("date", ""))

    # Load forgeries for this sender
    all_forged = []
    if os.path.exists(FORGED_FILE):
        with open(FORGED_FILE, "r", encoding="utf-8") as f:
            all_forged = [json.loads(line) for line in f if line.strip()]

    sender_forged = [l for l in all_forged if l.get("sender") == canon_id and l.get("tier") != "relabel"]

    generic_pool = sorted([l for l in sender_forged if l.get("tier") == "generic"], key=lambda x: x["text"][:30])
    styled_pool = sorted([l for l in sender_forged if l.get("tier") == "styled"], key=lambda x: x["text"][:30])
    short_pool = sorted([l for l in sender_forged if l.get("tier") == "short"], key=lambda x: x["text"][:30])

    selected_generic = rng.sample(generic_pool, 2) if len(generic_pool) >= 2 else generic_pool
    selected_styled = rng.sample(styled_pool, 2) if len(styled_pool) >= 2 else styled_pool
    selected_short = rng.sample(short_pool, 1) if len(short_pool) >= 1 else short_pool

    inbox_items = []
    slot = 1

    # Slots 1..8: Genuine holdout
    for m in selected_genuine:
        inbox_items.append({
            "id": f"{canon_id}_{slot:02d}",
            "sender": display_name,
            "subject": m.get("subject", "Corporate update"),
            "date": m.get("date", "2001-10-15")[:10],
            "body": m["body"],
            "category": "genuine_holdout",
        })
        slot += 1

    # Generic forgeries (2)
    generic_subjects = [
        "URGENT: Confidential Acquisition Remittance",
        "Updated Vendor Wire Banking Instructions",
    ]
    for idx, fitem in enumerate(selected_generic):
        inbox_items.append({
            "id": f"{canon_id}_{slot:02d}",
            "sender": display_name,
            "subject": generic_subjects[idx % len(generic_subjects)],
            "date": "2001-11-20",
            "body": fitem["text"],
            "category": "forged_generic",
        })
        slot += 1

    # Styled forgeries (2)
    styled_subjects = [
        "Transmission capacity and quarterly settlement",
        "Operational hedging review comments",
    ]
    for idx, fitem in enumerate(selected_styled):
        inbox_items.append({
            "id": f"{canon_id}_{slot:02d}",
            "sender": display_name,
            "subject": styled_subjects[idx % len(styled_subjects)],
            "date": "2001-11-25",
            "body": fitem["text"],
            "category": "forged_styled",
        })
        slot += 1

    # Short genuine (optional, 1)
    if short_genuine_rec is not None:
        inbox_items.append({
            "id": f"{canon_id}_{slot:02d}",
            "sender": display_name,
            "subject": short_genuine_rec.get("subject", "re: quick update"),
            "date": short_genuine_rec.get("date", "2001-11-28")[:10],
            "body": short_genuine_rec["body"],
            "category": "short_genuine",
        })
        slot += 1

    # Short forged evasion (1)
    for fitem in selected_short:
        inbox_items.append({
            "id": f"{canon_id}_{slot:02d}",
            "sender": display_name,
            "subject": "Wire transfer today",
            "date": "2001-11-30",
            "body": fitem["text"],
            "category": "short_forged_evasion",
        })
        slot += 1

    note = "" if has_short_genuine else "No genuine holdout message under 40 words exists; short genuine slot omitted."
    return InboxList(
        inbox_items,
        genuine_only=False,
        has_short_genuine=has_short_genuine,
        sender_id=canon_id,
        display_name=display_name,
        volume_class="high",
        note=note,
    )

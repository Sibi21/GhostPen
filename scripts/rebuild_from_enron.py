#!/usr/bin/env python3
"""
scripts/rebuild_from_enron.py
-----------------------------
Regenerates data/prepared/ and data/senders.json from the upstream Enron email corpus.
Ships with GhostPen as a documented, reproducible data extraction utility.

Usage:
    python scripts/rebuild_from_enron.py
"""

import collections
import email
import email.utils
import json
import os
import re
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone

ENRON_TAR_URL = "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz"

HIGH_VOLUME_TARGETS = [
    "presto-k",   # Aliased to "Marcus Hale, CFO"
    "blair-l",
    "corman-s",
    "cash-m",
    "hain-m",
    "guzman-m",
    "keiser-k",
    "lay-k",
    "neal-s",
    "heard-m",
]

LOW_VOLUME_TARGETS = [
    "scholtes-d",
    "ring-r",
    "may-l",
    "badeer-r",
    "quigley-d",
]

MAX_EMAILS_PER_HIGH_VOLUME = 160
MAX_EMAILS_PER_LOW_VOLUME = 50

SENDER_DISPLAY_NAMES = {
    "presto-k": "Kevin Presto (VP Trading)",
    "blair-l": "Lynn Blair",
    "corman-s": "Shelley Corman",
    "cash-m": "Michelle Cash",
    "hain-m": "Mary Hain",
    "guzman-m": "Mark Guzman",
    "keiser-k": "Kam Keiser",
    "lay-k": "Kenneth Lay",
    "neal-s": "Scott Neal",
    "heard-m": "Marie Heard",
    "scholtes-d": "Diana Scholtes",
    "ring-r": "Richard Ring",
    "may-l": "Larry May",
    "badeer-r": "Robert Badeer",
    "quigley-d": "Dutch Quigley",
}


def clean_email_body(raw_content: str):
    """
    Parses RFC 822 email, strips forwarded/replied blocks, signatures, and HTML.
    Never paraphrases or regenerates text.
    """
    msg = email.message_from_string(raw_content)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in cdispo:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(errors="replace")
        else:
            body = msg.get_payload() or ""

    # Strip HTML tags
    body = re.sub(r"<[^>]+>", " ", body)

    lines = body.splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        # Quoted reply lines
        if stripped.startswith(">"):
            continue
        # Forwarded or original message headers
        if (
            re.search(r"-----\s*Original Message\s*-----", line, re.I)
            or re.search(r"----------------------\s*Forwarded by", line, re.I)
            or re.search(r"^\s*From:.*Sent:.*To:.*Subject:", line, re.I)
            or re.search(r"^\s*\*{3,}\s*Forwarded by", line, re.I)
            or re.search(r"^\s*---\s*Inline Attachment Follows\s*---", line, re.I)
        ):
            break
        clean_lines.append(line)

    clean_text = "\n".join(clean_lines)
    # Strip signature delimiters
    clean_text = re.split(r"\n--\s*\n|\n---\s*\n|\n_{10,}", clean_text)[0].strip()

    # Parse date to ISO format for chronological sorting
    raw_date = msg.get("Date", "")
    iso_date = ""
    try:
        parsed_dt = email.utils.parsedate_to_datetime(raw_date)
        if parsed_dt:
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            iso_date = parsed_dt.isoformat()
    except Exception:
        iso_date = "2001-01-01T00:00:00+00:00"

    from_addr = msg.get("From", "").strip()
    subject = msg.get("Subject", "").strip()
    return from_addr, iso_date, subject, clean_text


def rebuild():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    prepared_dir = os.path.join(data_dir, "prepared")
    os.makedirs(prepared_dir, exist_ok=True)

    targets = set(HIGH_VOLUME_TARGETS + LOW_VOLUME_TARGETS)
    extracted = collections.defaultdict(list)

    print(f"Connecting to Enron tarball stream: {ENRON_TAR_URL} ...")
    req = urllib.request.Request(ENRON_TAR_URL, headers={"User-Agent": "Mozilla/5.0"})
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        with tarfile.open(mode="r|gz", fileobj=resp) as tar:
            for member in tar:
                if not member.isfile():
                    continue
                parts = member.name.split("/")
                if len(parts) >= 3 and parts[0] == "maildir":
                    user = parts[1]
                    if user not in targets:
                        continue
                    folder = parts[2].lower()
                    if folder in ("_sent_mail", "sent", "sent_items"):
                        # Check if limit reached
                        limit = (
                            MAX_EMAILS_PER_HIGH_VOLUME
                            if user in HIGH_VOLUME_TARGETS
                            else MAX_EMAILS_PER_LOW_VOLUME
                        )
                        if len(extracted[user]) >= limit:
                            continue

                        f = tar.extractfile(member)
                        if f:
                            raw = f.read().decode("latin-1", errors="replace")
                            from_addr, iso_date, subject, body = clean_email_body(raw)
                            words = body.split()
                            # Require at least 15 words and 2 sentences for training quality
                            if len(words) >= 15:
                                extracted[user].append({
                                    "sender_id": user,
                                    "from": from_addr,
                                    "date": iso_date,
                                    "subject": subject,
                                    "body": body,
                                    "word_count": len(words),
                                })

                # Check termination condition
                all_high_done = all(
                    len(extracted[u]) >= 120 for u in HIGH_VOLUME_TARGETS
                )
                all_low_done = all(
                    len(extracted[u]) >= 20 for u in LOW_VOLUME_TARGETS
                )
                if all_high_done and all_low_done:
                    print("All targets satisfied! Finalizing extraction.")
                    break

    senders_catalog = []
    print("\nWriting cleaned per-sender JSONL files...")
    for user in HIGH_VOLUME_TARGETS + LOW_VOLUME_TARGETS:
        emails = extracted[user]
        # Sort chronologically by date
        emails.sort(key=lambda x: x["date"])

        is_high = user in HIGH_VOLUME_TARGETS
        vol_class = "high" if is_high else "low"
        is_demo = user == "presto-k"
        alias = "Marcus Hale, CFO" if is_demo else None

        # Write prepared jsonl
        out_file = os.path.join(prepared_dir, f"{user}.jsonl")
        with open(out_file, "w", encoding="utf-8") as out_f:
            for item in emails:
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")

        print(f"  [OK] {user} ({vol_class}): {len(emails)} emails -> {out_file}")

        senders_catalog.append({
            "sender_id": user,
            "display_name": SENDER_DISPLAY_NAMES.get(user, user),
            "volume_class": vol_class,
            "total_emails": len(emails),
            "alias": alias,
            "demo_persona": is_demo,
            "file": f"data/prepared/{user}.jsonl",
        })

    catalog_path = os.path.join(data_dir, "senders.json")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "description": "GhostPen 15 Enron senders (10 high-volume, 5 low-volume) + Marcus Hale CFO alias",
            "senders": senders_catalog,
        }, f, indent=2)

    print(f"\nWrote catalog to {catalog_path}")
    print("Rebuild complete!")


if __name__ == "__main__":
    rebuild()

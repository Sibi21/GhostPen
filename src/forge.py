"""
src/forge.py
------------
Generates and audits the 4-tier forged evaluation corpus:
- Tier 'relabel': Emails drawn from OTHER senders' HOLDOUT sets (clean test docs for baselines).
- Tier 'generic': Fluent LLM-style BEC emails (urgent wire, payroll, gift cards, invoices).
- Tier 'styled': Attacker impersonations written in the target sender's specific voice (60-120 words).
- Tier 'short': Evasion plays (15-30 words) designed to test the abstain-and-route layer.

Includes the mandatory Tier C Copy Audit:
Calculates distinct shared word-5-grams and longest common substring (LCS)
against the target's training corpus. Flags as 'copy_based' if shared 5-grams > 5 OR LCS > 60 chars.
"""

import collections
import json
import os
from typing import Dict, List, Set, Tuple

from src.ingest import get_all_senders, split_sender_data

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FORGED_DIR = os.path.join(DATA_DIR, "forged")
FORGED_FILE = os.path.join(FORGED_DIR, "forged.jsonl")

# 10 Distinct Generic BEC Email Templates (LLM-style prose, 60-150 words)
GENERIC_BEC_TEMPLATES = [
    """Dear Finance Team,
I am currently in an urgent and strictly confidential executive committee meeting regarding the pending international asset acquisition. We have reached an expedited agreement that necessitates an immediate settlement payment today before close of business.
Kindly execute an urgent wire transfer in the amount of $248,500 to the overseas escrow account specified in the attached documentation. Please ensure this invoice is processed forthwith and treat this matter with the highest level of discretion.
Reply only to me via this email thread once the transfer confirmation has been generated.
Best regards!""",

    """Good morning,
Please note that our primary vendor has updated their banking coordinates for all outstanding disbursements effective immediately. We must wire the balance of $96,400 to the new bank account today to prevent any disruption to supply operations. Attached is the revised invoice.
Treat this request as strictly confidential and ensure the wire is sent before the 3:00 PM cutoff.
Sincerely,""",

    """Hi,
I need an urgent favor before I step into an executive committee session. Could you please purchase fifteen $100 Apple gift cards for the upcoming employee appreciation lunch? Please scratch the backs and email clear photos of the codes directly to me today.
I will provide the corporate card reconciliation tomorrow once I return to the office.
Best regards,""",

    """Dear Payroll Department,
I need to update my direct deposit bank account information for the upcoming payroll cycle starting this week. Please find my updated routing and account numbers attached in the formal bank authorization letter.
Kindly confirm once this change has been recorded in the central payroll system today.
Kind regards,""",

    """Urgent Attention Required:
Pursuant to our quarterly audit review, we are obligated to settle the outstanding legal retainer balance immediately. Kindly execute a wire transfer in the amount of $142,000 to counsel's trust bank account before the 3:00 PM cutoff today.
Treat this communication with the strictest confidentiality and advise once completed.
Best regards,""",

    """Hello Team,
We have an expedited software licensing contract renewal that must be finalized today to retain our volume pricing discount. Kindly process an emergency wire transfer of $78,250 to the vendor bank account specified in the attached invoice.
Reply only to me with the payment receipt confirmation today.
Regards,""",

    """Dear Accounting,
Please arrange an immediate wire transfer of $215,000 to fund the initial earnest deposit for our commercial facility leasehold. The closing documents require funds to be cleared today before 4:00 PM.
Please treat this transaction as confidential and confirm execution as soon as possible.
Sincerely,""",

    """Good day,
Our tax advisory firm has advised that an expedited corporate tax payment must be wired to the state treasury department today to avoid statutory interest penalties. Please execute the wire transfer of $64,800 immediately to the bank account listed on the formal assessment notice.
Kind regards,""",

    """Hi Team,
I am offsite today and have limited phone access during regulatory interviews. We need to remit an emergency vendor retainer payment of $118,000 before the end of business today.
Please process this wire transfer immediately to the account on file and reply only to me once completed.
Best,""",

    """Confidential Executive Notice:
Please execute an immediate wire transfer in the amount of $325,000 for the settlement of our strategic partnership agreement. Wire instructions for the recipient bank are attached.
This matter is strictly confidential — do not discuss with outside parties and reply only to me today.
Best regards!""",
]

# 2 Short Evasion Plays (15-30 words, with >= 2 context flags)
SHORT_EVASION_TEMPLATES = [
    "Need this closed today. Wire the balance to the updated account. Confidential acquisition. Reply only to me. Thanks.",
    "Please process the wire transfer for the vendor today before cutoff. Details are in the invoice. Keep confidential and reply only to me.",
]

# 5 Tailored Impersonations per High-Volume Sender (Tier C, 60-120 words)
# Careful attacker imitates sender's voice, greeting, and signoff habits
STYLED_BEC_PROMPTS = {
    "presto-k": [
        "Regarding the physical power scheduling for next week, we need to adjust the New Albany transmission capacity allocations prior to the cash market close. The bilateral counterparties have confirmed the revised volumes. Please execute a wire transfer of $145,000 to the updated settlement account today before 2:00 PM to avoid contract penalties. I will follow up with credit regarding the documentation. Reply only to me. Thanks.",
        "Below are the revised settlement assumptions for booking the East Power congestion book. The counterparty has requested immediate funds clearance prior to scheduling physical flow tomorrow morning. Wire the $88,000 balance to our counterparty account today. Need confirmation when completed. Thanks.",
        "We need to fund the East Power trading margin deposit immediately to prevent scheduling curtailment. Please call the settlement desk and wire $210,000 to the clearinghouse bank today before 3pm. Keep this matter confidential between desk heads. Thanks.",
        "Please check with credit on the bilateral counterparty settlement wire for $175,000. We agreed with Calger to close the bilateral position today. We need to execute the wire transfer today to maintain physical scheduling across the grid. Reply only to me with the confirmation number. Thanks.",
        "Regarding the TVA transmission interconnect fee, the operator has updated their clearing instructions for the month. Wire $125,000 to their operating bank account before 4pm today so we can finalize the booking numbers. Let me know when this is out. Thanks.",
    ],
    "blair-l": [
        "Shelley, FYI. Just to let you know our practice on the pipeline interconnect project. We need to process an emergency wire transfer of $94,000 for the pipeline contractor balance today. Let's make sure this gets scheduled immediately before the afternoon nomination deadline. Is there anything else you need from us on this? Thanks. Lynn",
        "Tammy, let's go forward with the vendor payment today. Please wire the $62,000 balance to the updated account on the attached invoice so we don't hold up the training schedule. Let me know if you have any questions before processing. Thanks. Lynn",
        "Terry, just to let you know our practice on the capacity nomination fee. We must wire $85,000 to the transmission operator bank today to ensure uninterrupted transport service. Shelley agreed to the revised terms earlier this morning. Thanks. Lynn",
        "Shelley, please review the attached urgent wire request for $115,000 regarding the transport imbalances. We need to clear this before the end of the day today. Keep me posted once the bank confirms. Thanks. Lynn",
        "John, let's execute the transport imbalance settlement wire today for $78,000. This is a confidential matter concerning the pipeline audit. Please confirm once the transfer is finalized. Thanks. Lynn",
    ],
    "corman-s": [
        "Jackie, looks good. In addition to the committee review, we need to process an urgent wire transfer of $86,000 for the regulatory filing balance today. I guess we just need to make sure the accounting group clears the voucher before 3pm. Let me know if you need anything else from my end. Thanks. Shelley",
        "Letter looks good. Just a few thoughts: please ensure the vendor wire for $112,000 is transferred to the updated account today before cutoff. We want to avoid any friction with outside counsel while these filings are pending. Keep me updated. Shelley",
        "Thanks looks good. We also have an urgent committee requirement to wire $95,000 to our legal counsel bank today. Please keep this confidential until the formal announcement next week. Thanks for your help with this. Shelley",
        "Jackie, here is the updated payment schedule for the regulatory group. Please wire the $130,000 deposit to the escrow account today so we can finalize the docket submission. Let's touch base after lunch. Shelley",
        "Please review the attached invoice from our consulting team. I need this wire transfer sent to the vendor today without delay. Reply only to me once the confirmation comes through. Thanks. Shelley",
    ],
    "cash-m": [
        "Twanda, would you please prepare an urgent wire transfer of $165,000 for the legal settlement and process it today? I think we should also have Jordan Mintz review the final release, but the funds must clear before the 4pm deadline. Thanks a lot. Michelle",
        "Greg, we have to get together soon regarding the tax structure. In the meantime, please wire the $120,000 retainer to our outside counsel's trust account today. Treat this as strictly confidential. Thanks a lot. Michelle",
        "Twanda, would you please save these documents to my form directory and print them out for me? Also, please ensure the wire confirmation for the $95,000 arbitration escrow payment is sent today. Thanks a lot. Michelle",
        "We need to execute an immediate wire transfer for the outside counsel fees of $140,000 today. Jordan Mintz approved the expense allocation earlier this morning. Please confirm once completed. Michelle",
        "Twanda, please wire the $82,000 balance to the bank account attached today. This relates to our confidential employment agreement and must go out before close of business. Thanks a lot. Michelle",
    ],
    "hain-m": [
        "I asked Chris to forward you this information in response to the emergency data request. We must remit a wire transfer of $175,000 to the regulatory compliance bank account today before the formal deadline. Please review the attached filing and advise once the funds have been dispatched. Mary",
        "Many thanks! In response to data request Number 8, we are obligated to wire $120,000 for the market monitoring assessment before the end of business today. Please call me if you have any questions regarding the account coordinates. Mary",
        "I'm sending you a series of documents regarding the FERC settlement proceeding. Please wire the $98,000 administrative fee to the designated account today. Treat this communication as strictly confidential. Many thanks. Mary",
        "Please review the attached data request and wire the $145,000 consulting retainer to our economic expert today. Before EPMI submits the response, we need this payment confirmed by the bank. Mary",
        "Many thanks for handling this quickly. We need the wire transfer of $88,000 executed today to complete the compliance filing with the commission. Reply only to me with confirmation. Mary",
    ],
    "guzman-m": [
        "What up foolio? Just thought I would drop you a line. We got an urgent scheduling imbalance on the California border that requires us to wire $92,000 today before 3pm. Keep it quiet between our group for now. Thanks Guzman",
        "Evelyn and Kim, please let your group know to execute the wire transfer of $110,000 to the Portland desk account today. We need this settled before the real-time scheduling window closes. Let me know when it's done. Mark",
        "Hey man, can you please wire the $85,000 broker fee to the updated bank account today? Need this done ASAP so our power deliveries don't get cut off at the border. Confirm once sent. Mark",
        "What up? We got an urgent margin wire for $130,000 that has to go out today before the power schedule closes. Let's make sure the desk accounts are balanced. Thanks Guzman",
        "Please add this wire transfer of $75,000 to the morning run today. Confidential transaction for the west desk scheduling team. Thanks Mark",
    ],
    "keiser-k": [
        "I started calculating the bankruptcy book last night and we need an emergency margin wire of $150,000 to the clearing broker today. Errol and Jeff agreed this needs to be funded immediately before cutoff. Thanks Kam",
        "Francis, can you execute the wire transfer of $98,000 when you are done? Need this completed before the credit cutoff today. Please call Errol when finished. Thanks Kam",
        "Please add this wire request to the daily book. We need $125,000 wired to the counterparty bank account today to cover the overnight risk exposure. Let me know once sent. Thanks Kam",
        "Errol and Jeff, please confirm once the wire transfer of $85,000 has been sent to the risk reserve account today. We need this in the nightly numbers. Thanks Kam",
        "Nightly credit requirement: please wire $140,000 to the collateral bank account today before 5pm. Keep this confidential and reply only to me. Thanks Kam",
    ],
    "lay-k": [
        "Hi - We did receive the executive committee memo. Please arrange an immediate wire transfer of $250,000 for the advisory council engagement today. Rosalee will coordinate the documentation. Keep this matter strictly confidential. Ken Lay",
        "Rosalee for Ken Lay: Please ensure a confidential wire transfer of $180,000 is sent to the foundation bank account today. Mr. Lay has authorized this disbursement for immediate clearance. Thank you.",
        "Regarding the aircraft charter agreement, please wire $300,000 for the leasehold deposit today before close of business. Rosalee has the banking instructions on file. Ken Lay",
        "Hi - We need this wire transfer executed today for the corporate aircraft account balance of $125,000. Please confirm once the transaction is completed with the bank. Ken Lay",
        "Rosalee for Ken Lay: Mr. Lay has requested an expedited wire transfer of $210,000 to our external counsel today. Treat this request with the highest level of confidentiality.",
    ],
    "neal-s": [
        "i will be there. please also make sure the $115,000 wire transfer is sent to the gas trading settlement account today before 2pm. Tammi has the updated coordinates. Scott",
        "thanks for the info. Tammi, please wire $95,000 to the pipeline counterparty bank account today before the trade cutoff. We need this cleared to maintain transport capacity. Scott",
        "Absolutely! Can you also wire the $140,000 balance to the physical scheduling account today? Let's make sure the East desk numbers balance out tonight. Scott",
        "Colleen, please process the wire transfer of $88,000 for the East desk trading run today. Keep this confidential until the book is closed. Scott",
        "thanks for handling this. Need $105,000 wired to the settlement bank account today before close of business. Reply only to me. Scott",
    ],
    "heard-m": [
        "Pursuant to Sara Shackleton's request, please execute a wire transfer of $165,000 for the ISDA master agreement collateral today. The documentation has been verified and requires clearance before 3pm. Marie",
        "Hi, Bianca! Francisco has asked me to request an immediate wire transfer of $120,000 to the counterparty escrow bank today. Please confirm once the wire instructions have been transmitted. Marie",
        "Pursuant to our discussion regarding the swap confirmation, please wire $95,000 to the legal retainer account today before the afternoon cutoff. Thanks. Marie",
        "I am attaching the documentation for the deemed ISDA settlement. Please process the wire transfer of $140,000 today. Treat this matter as strictly confidential. Marie",
        "Bianca, please confirm once the wire transfer of $110,000 has been transmitted to the bank today. Francisco and Sara need the confirmation for the closing file. Thanks. Marie",
    ],
}


def compute_word_5grams(text: str) -> Set[str]:
    """Extracts contiguous word 5-grams from text."""
    words = text.lower().split()
    if len(words) < 5:
        return set()
    return set(" ".join(words[i : i + 5]) for i in range(len(words) - 4))


def longest_common_substring(s1: str, s2: str) -> int:
    """Computes length of longest common substring between two strings."""
    s1_clean = " ".join(s1.lower().split())
    s2_clean = " ".join(s2.lower().split())
    m, n = len(s1_clean), len(s2_clean)
    if m == 0 or n == 0:
        return 0

    dp = [0] * (n + 1)
    max_len = 0
    for i in range(1, m + 1):
        prev = 0
        for j in range(1, n + 1):
            temp = dp[j]
            if s1_clean[i - 1] == s2_clean[j - 1]:
                dp[j] = prev + 1
                if dp[j] > max_len:
                    max_len = dp[j]
            else:
                dp[j] = 0
            prev = temp
    return max_len


def audit_styled_forgery(styled_text: str, train_emails: List[Dict]) -> Dict:
    """
    Mandatory Tier C Copy Audit:
    Computes distinct shared word-5-grams and longest common substring (LCS)
    against all training emails of the sender.
    Flags copy_based = True if shared_5grams > 5 OR max_lcs_len > 60 chars.
    """
    styled_5grams = compute_word_5grams(styled_text)
    shared_5grams_all = set()
    max_lcs = 0

    for email_obj in train_emails:
        body = email_obj.get("body", "")
        # 5-grams
        train_5grams = compute_word_5grams(body)
        shared = styled_5grams.intersection(train_5grams)
        shared_5grams_all.update(shared)

        # LCS
        lcs_len = longest_common_substring(styled_text, body)
        if lcs_len > max_lcs:
            max_lcs = lcs_len

    is_copy_based = len(shared_5grams_all) > 5 or max_lcs > 60
    return {
        "copy_based": is_copy_based,
        "shared_5grams_count": len(shared_5grams_all),
        "shared_5grams": sorted(list(shared_5grams_all)),
        "max_lcs_len": max_lcs,
    }


def generate_forged_dataset() -> List[Dict]:
    """
    Constructs the 4-tier forged dataset (270 total records) across 10 high-volume senders:
    - Tier 'relabel': 10 emails from other senders' holdout windows (10 * 10 = 100)
    - Tier 'generic': 10 LLM-style BEC emails (10 * 10 = 100)
    - Tier 'styled': 5 voice-imitating BEC emails (5 * 10 = 50)
    - Tier 'short': 2 evasion plays (2 * 10 = 20)
    """
    os.makedirs(FORGED_DIR, exist_ok=True)
    all_senders = get_all_senders()
    high_senders = [s["sender_id"] for s in all_senders if s["volume_class"] == "high"]

    # Gather holdout emails for relabel pool
    sender_holdouts = {}
    sender_trains = {}
    for sid in high_senders:
        train_set, holdout_set = split_sender_data(sid)
        sender_trains[sid] = train_set
        # Filter holdout emails with reasonable length (60 to 150 words)
        candidate_holdouts = [
            e["body"] for e in holdout_set if 50 <= len(e["body"].split()) <= 160
        ]
        sender_holdouts[sid] = candidate_holdouts

    records = []
    copy_audit_results = {}

    print(f"Generating 4-tier forged corpus across {len(high_senders)} high-volume senders...")

    for i, target_sid in enumerate(high_senders):
        # 1. Tier Relabel (10 emails from other senders' holdouts)
        other_senders = [s for s in high_senders if s != target_sid]
        relabel_emails = []
        for other_sid in other_senders:
            relabel_emails.extend(sender_holdouts[other_sid])
            if len(relabel_emails) >= 10:
                break
        
        # Take exactly 10
        for r_text in relabel_emails[:10]:
            records.append({
                "sender": target_sid,
                "tier": "relabel",
                "text": r_text,
            })

        # 2. Tier Generic (10 distinct templates)
        for g_text in GENERIC_BEC_TEMPLATES:
            records.append({
                "sender": target_sid,
                "tier": "generic",
                "text": g_text,
            })

        # 3. Tier Styled (5 voice-imitating attacks, 60-120 words)
        styled_texts = STYLED_BEC_PROMPTS.get(target_sid, [])
        for s_idx, s_text in enumerate(styled_texts):
            # Run Copy Audit
            audit_res = audit_styled_forgery(s_text, sender_trains[target_sid])
            audit_key = f"{target_sid}_styled_{s_idx}"
            copy_audit_results[audit_key] = audit_res

            records.append({
                "sender": target_sid,
                "tier": "styled",
                "text": s_text,
                "copy_based": audit_res["copy_based"],
                "shared_5grams_count": audit_res["shared_5grams_count"],
                "max_lcs_len": audit_res["max_lcs_len"],
            })

        # 4. Tier Short (2 evasion plays)
        for s_evasion in SHORT_EVASION_TEMPLATES:
            records.append({
                "sender": target_sid,
                "tier": "short",
                "text": s_evasion,
            })

    # Save to data/forged/forged.jsonl
    with open(FORGED_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n[OK] Wrote {len(records)} forged evaluation records to {FORGED_FILE}")
    tier_counts = collections.Counter(r["tier"] for r in records)
    for t, c in tier_counts.items():
        print(f"  Tier '{t}': {c} emails")

    # Copy audit summary
    copy_based_cnt = sum(1 for a in copy_audit_results.values() if a["copy_based"])
    total_styled = len(copy_audit_results)
    print(f"\nTier C Copy Audit:")
    print(f"  Total Styled Forgeries: {total_styled}")
    print(f"  Tagged as 'copy_based': {copy_based_cnt} ({copy_based_cnt/total_styled*100:.1f}%)")
    print(f"  Style-imitation clean:  {total_styled - copy_based_cnt}")

    return records


if __name__ == "__main__":
    generate_forged_dataset()

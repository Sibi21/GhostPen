"""
src/cli.py
----------
Command-line interface for GhostPen.
Usage:
    python -m src.cli --sender "Marcus Hale" --file email.txt
    python -m src.cli --sender "Marcus Hale" --text "Please review the wire..."
    python -m src.cli --demo
"""

import argparse
import json
import sys
from typing import Optional

from src.attribution import compute_attribution
from src.ingest import display_name
from src.score import score_message


def run_cli():
    parser = argparse.ArgumentParser(
        description="GhostPen: BEC Detection via Writing-Style Verification."
    )
    parser.add_argument(
        "--sender",
        type=str,
        default=None,
        help="Sender name, email, or alias (e.g., 'Marcus Hale (CFO)', 'presto-k')",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to text file containing the email body to evaluate",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Raw email body text directly on the command line",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        choices=[0.02, 0.05, 0.10],
        help="Operating significance level alpha (default: 0.05)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run interactive CLI demonstration on sample genuine and forged messages",
    )

    args = parser.parse_args()

    if args.demo:
        run_demo_cli(args.alpha)
        return

    if not args.sender:
        print("Error: --sender is required unless running with --demo.", file=sys.stderr)
        sys.exit(1)

    text = ""
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file '{args.file}': {e}", file=sys.stderr)
            sys.exit(1)
    elif args.text is not None:
        text = args.text
    else:
        # Read from stdin if piped
        if not sys.stdin.isatty():
            text = sys.stdin.read()
        else:
            print("Error: either --file, --text, or piped stdin must be provided.", file=sys.stderr)
            sys.exit(1)

    result = score_message(text, args.sender, alpha=args.alpha)
    print(json.dumps(result, indent=2))

    v = result["verdict"]
    esc = result["content_escalation"]
    if v == "ALERT" or (v == "TRIAGE" and esc):
        att = compute_attribution(text, args.sender, alpha=args.alpha)
        print("\nClosest enrolled authors (among 15 enrolled senders - suggestion, not identification; never affects S or the verdict):")
        if att["is_no_match"]:
            print("  No enrolled author's style matches this message.")
        else:
            for idx, m in enumerate(att["top_3"]):
                print(f"  #{idx + 1}: {m['display_name']} (p={m['p']:.4f})")
        print(f"  Claimed sender ({att['claimed_sender']['display_name']}): p={att['claimed_sender']['p']:.4f}")
    elif v == "OK":
        print(f"\nVerified as {display_name(args.sender).split(' (')[0]}. Attribution ranking is shown only for rejected messages.")
    elif v == "TRIAGE":
        print("\nStylometry abstained - no attribution suggested.")


def run_demo_cli(alpha: float = 0.05):
    """Demonstrates scoring across genuine, forged, and short-evasion scenarios."""
    print("=" * 70)
    print(" GhostPen CLI Demo — Target Sender: Marcus Hale (CFO)")
    print(f" Operating Alpha: {alpha}")
    print("=" * 70)

    sample_cases = [
        (
            "1. Genuine Holdout Email (Full Length)",
            """I apologize for my earlier comments. Everyone is having a rough time with the current meltdown of the company. I have been here 7 years and I am seeing everything I worked for coming to an end.

It's not your fault and I do apologize.""",
        ),
        (
            "2. BEC Impersonation Attack (Generic LLM Style)",
            """Dear Finance Team,
I am currently in an urgent meeting with our external legal counsel regarding confidential acquisition proceedings. 
Kindly execute an immediate wire transfer in the amount of $184,500 to the updated vendor bank account attached. 
Please ensure this transfer is executed today without delay. Reply only to me with confirmation.
Best regards!""",
        ),
        (
            "3. Short Benign Email (<40 words)",
            """ok thx. lets discuss after the 2pm committee call.""",
        ),
        (
            "4. Short Forged Wire Evasion Email (22 words with context flags)",
            """Need this closed today. Wire the balance to the updated account. Confidential acquisition. Reply only to me. Thanks.""",
        ),
    ]

    for title, text in sample_cases:
        print(f"\n--- {title} ---")
        print(f"Body snippet:\n\"{text.strip()}\"\n")
        res = score_message(text, "Marcus Hale", alpha=alpha)
        
        # Format human-readable summary
        verdict = res["verdict"]
        p_val = res["p"]
        s_score = res["deviation_score"]
        flags = res["context_flags"]
        escalate = res["content_escalation"]

        print(f"  Verdict:            {verdict}")
        print(f"  Deviation Score S:  {s_score:.4f}")
        print(f"  Conformal p-value:  {p_val:.4f} (p_min={res['p_min']:.4f})")
        print(f"  Reason:             {res['reason']}")
        if res["direction"] != "Style variation within normal baseline":
            print(f"  Direction:          {res['direction']}")
        if res["broken_habits"]:
            print("  Broken Habits:")
            for bh in res["broken_habits"]:
                print(f"    - {bh}")
        if flags:
            print(f"  Context Flags:      {flags}")
        if escalate:
            print(f"  [!] ESCALATION:     {res['escalation_hint']}")

        if verdict == "ALERT" or (verdict == "TRIAGE" and escalate):
            att = compute_attribution(text, "Marcus Hale", alpha=alpha)
            print("  Attribution (Closest enrolled authors):")
            if att["is_no_match"]:
                print("    No enrolled author's style matches this message.")
            else:
                for idx, m in enumerate(att["top_3"]):
                    print(f"    #{idx + 1}: {m['display_name']} (p={m['p']:.4f})")
            print(f"    Claimed ({att['claimed_sender']['display_name']}): p={att['claimed_sender']['p']:.4f}")
        elif verdict == "OK":
            print("  Verified as Marcus Hale. Attribution ranking is shown only for rejected messages.")
        elif verdict == "TRIAGE":
            print("  Stylometry abstained - no attribution suggested.")


if __name__ == "__main__":
    run_cli()

"""
scripts/check_ready.py
----------------------
Pre-flight readiness verification for GhostPen.
Confirms Python version, package imports, required project files,
self-heals missing profiles if needed, and runs an end-to-end scoring check.
Exits with 0 if ready, 1 with troubleshooting guidance if not.
"""

import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def check_python_version():
    major, minor = sys.version_info.major, sys.version_info.minor
    if major < 3 or (major == 3 and minor < 10):
        print(f"[FAIL] Python version is {major}.{minor}. GhostPen requires Python 3.10 or newer.")
        print("       Please install Python 3.10+ from https://www.python.org/downloads/")
        return False
    print(f"[OK] Python version: {major}.{minor}.{sys.version_info.micro} (>= 3.10)")
    return True


def check_dependencies():
    missing = []
    packages = [
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("sklearn", "scikit-learn"),
        ("matplotlib", "matplotlib"),
        ("streamlit", "streamlit"),
    ]
    for module_name, pip_name in packages:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[FAIL] Missing required package(s): {', '.join(missing)}")
        print("       Please run: pip install -r requirements.txt")
        return False
    print("[OK] Dependencies verified: numpy, pandas, scikit-learn, matplotlib, streamlit")
    return True


def check_project_files():
    required_paths = [
        os.path.join(REPO_ROOT, "app", "app.py"),
        os.path.join(REPO_ROOT, "app", "demo_inbox.json"),
        os.path.join(REPO_ROOT, "src", "features.py"),
        os.path.join(REPO_ROOT, "src", "profile.py"),
        os.path.join(REPO_ROOT, "src", "score.py"),
        os.path.join(REPO_ROOT, "data", "senders.json"),
        os.path.join(REPO_ROOT, "data", "prepared"),
    ]

    for p in required_paths:
        if not os.path.exists(p):
            rel = os.path.relpath(p, REPO_ROOT)
            print(f"[FAIL] Required file or directory missing: {rel}")
            return False

    # Check that prepared jsonl files exist
    prep_dir = os.path.join(REPO_ROOT, "data", "prepared")
    prep_files = [f for f in os.listdir(prep_dir) if f.endswith(".jsonl")]
    if len(prep_files) < 15:
        print(f"[FAIL] Found only {len(prep_files)} prepared sender files in data/prepared/ (expected >= 15).")
        return False

    print(f"[OK] Project files & Enron dataset verified ({len(prep_files)} senders in data/prepared/)")
    return True


def check_or_rebuild_profiles():
    profiles_file = os.path.join(REPO_ROOT, "artifacts", "profiles.json")
    nulls_file = os.path.join(REPO_ROOT, "artifacts", "nulls.json")

    if not os.path.exists(profiles_file) or not os.path.exists(nulls_file):
        print("[INFO] Profiles or null distributions missing. Self-healing: rebuilding now...")
        try:
            from src.profile import build_all_profiles
            build_all_profiles()
            print("[OK] Rebuilt profiles.json and nulls.json successfully.")
        except Exception as e:
            print(f"[FAIL] Failed to automatically rebuild profiles: {e}")
            return False
    else:
        print("[OK] Executive habit profiles & null distributions verified")
    return True


def check_scoring_engine():
    try:
        from src.score import score_message
        test_text = (
            "Please review the attached invoice schedule for our quarterly payment. "
            "Let me know if you have any questions before we finalize the transfer tomorrow."
        )
        res = score_message(test_text, "Marcus Hale", alpha=0.05)
        if "verdict" not in res or res["verdict"] not in ["OK", "ALERT", "TRIAGE", "UNENROLLED"]:
            print(f"[FAIL] Scoring engine returned invalid response: {res}")
            return False
    except Exception as e:
        print(f"[FAIL] Scoring engine sanity check failed: {e}")
        return False

    print("[OK] Stylometric scoring engine operational")
    return True


def main():
    print("=" * 60)
    print(" GhostPen Pre-Flight Readiness Check")
    print("=" * 60)

    checks = [
        check_python_version,
        check_dependencies,
        check_project_files,
        check_or_rebuild_profiles,
        check_scoring_engine,
    ]

    all_passed = True
    for check in checks:
        if not check():
            all_passed = False
            break

    print("-" * 60)
    if all_passed:
        print("GhostPen is ready to launch!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("Readiness check failed. Please resolve the issues above.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

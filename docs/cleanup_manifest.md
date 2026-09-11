# Cleanup Manifest (PATCH P11 — Repo Hygiene)

| Deleted Path | Category | Rationale |
| :--- | :--- | :--- |
| .chrome_temp_verify/ | Untracked Ephemeral Cache | 104 MB temporary Chrome browser profile and cache created during headless verification; not needed at runtime. |
| pp/demo_inbox.json | Redundant Duplicate | 7 KB byte-identical duplicate of data/demo_inbox.json; all runtime and evaluation modules read from data/demo_inbox.json. |
| scripts/capture_mailbox_screenshot.py | Ad-hoc Developer Tooling | One-off DevTools screenshot script used during Patch P5; the produced artifact image rtifacts/mailbox_table_screenshot.png is permanently preserved. |
| scripts/capture_sidebar_screenshot.py | Ad-hoc Developer Tooling | One-off DevTools screenshot script used during Patch P5; the produced artifact image rtifacts/sidebar_screenshot.png is permanently preserved. |

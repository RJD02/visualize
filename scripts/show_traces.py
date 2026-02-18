#!/usr/bin/env python3
"""Quick script to display agent traces for a session."""
import json
import sys
import urllib.request

session_id = sys.argv[1] if len(sys.argv) > 1 else "70e4f67b-2bb9-4b64-ae4d-44b3301ea542"
url = f"http://localhost:8000/api/sessions/{session_id}/traces"

with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read())

print(f"Total traces: {data['total']}\n")
for t in data["traces"]:
    step = str(t["step_index"]) if t["step_index"] is not None else "-"
    err = f" ERROR: {t['error']}" if t.get("error") else ""
    print(f"  [{step:>4}] {t['agent_name']:35s} | {str(t['decision']):45s} | {t['duration_ms']}ms{err}")

#!/usr/bin/env python3
"""Test script: create a session and ingest a GitHub repo to generate diagrams.
Run from project root with PYTHONPATH set to project root.
"""
import os
import sys
from uuid import UUID

# ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.db import SessionLocal
from src.services.session_service import create_session, ingest_input, list_images, list_ir_versions

GITHUB_URL = "https://github.com/rishianshu/jira_plus_plus/"


def main():
    db = SessionLocal()
    try:
        session = create_session(db)
        print("Created session:", session.id)
        result = ingest_input(db, session, files=None, text=None, github_url=GITHUB_URL)
        print("Ingest result keys:", list(result.keys()))
        images = list_images(db, session.id)
        print(f"Generated {len(images)} images")
        for img in images:
            print("- image:", img.id, "version", img.version, img.file_path)
            if os.path.exists(img.file_path):
                size = os.path.getsize(img.file_path)
                print("  file exists, size:", size)
                if img.file_path.endswith('.svg'):
                    with open(img.file_path, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    print("  svg length:", len(txt))
                    print('  svg head sample:')
                    print(txt[:800])
            else:
                print("  file missing on disk")
        irs = list_ir_versions(db, session.id)
        print(f"Stored {len(irs)} IR versions")
        for ir in irs:
            print("- ir:", ir.id, "type", ir.diagram_type, "version", ir.version, "len(svg_text)", len(ir.svg_text))
    finally:
        db.close()


if __name__ == '__main__':
    main()

import sys
import os

# Ensure the parent directory is in the path so all modules resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: F401 — Vercel picks up the `app` object

"""Pons — ponte entre o celular e o computador."""
import os
import sys

__version__ = "1.0.0"
APP_NAME = "Pons"
APP_ID = "Pons"
AUTHOR = "Lohan Lilson S. Lopes"
EMAIL = "lohanlilson@gmail.com"
COPYRIGHT = f"© 2026 {AUTHOR}"
UPDATE_REPO = "lohanlilson/Pons"


def resource(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def pasta_dados(*partes):
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~/.local/share")
    p = os.path.join(base, "Pons", *partes)
    os.makedirs(p, exist_ok=True)
    return p

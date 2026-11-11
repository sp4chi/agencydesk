"""Create .env from .env.example, filling SESSION_SECRET with a random value.

Never overwrites an existing .env. Used by `make env`.
"""
import pathlib
import secrets

ROOT = pathlib.Path(__file__).resolve().parent.parent
target = ROOT / ".env"

if target.exists():
    print(".env already exists, leaving it alone")
else:
    lines = (ROOT / ".env.example").read_text().splitlines()
    lines = [
        f"SESSION_SECRET={secrets.token_urlsafe(48)}" if line.startswith("SESSION_SECRET=") else line
        for line in lines
    ]
    target.write_text("\n".join(lines) + "\n")
    print("wrote .env with a fresh SESSION_SECRET")

"""Password hashing with bcrypt (cost 12).

bcrypt only looks at the first 72 bytes of a password, and bcrypt>=5
refuses longer input. We reject over-long passwords explicitly rather
than silently truncating them.
"""
import bcrypt

BCRYPT_ROUNDS = 12
MAX_PASSWORD_BYTES = 72

# Checked against when the email is unknown, so "no such user" takes as
# long as "wrong password" and response timing doesn't reveal which emails
# have accounts. It is a hash of a random value nobody knows.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser-not-a-real-password", bcrypt.gensalt(BCRYPT_ROUNDS))


def hash_password(password: str) -> str:
    raw = password.encode()
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    """True only if password_hash is set and matches. Always costs one bcrypt check,
    pass password_hash=None for an unknown user to keep timing the same."""
    raw = password.encode()
    too_long = len(raw) > MAX_PASSWORD_BYTES
    stored = password_hash.encode() if password_hash else _DUMMY_HASH
    try:
        matches = bcrypt.checkpw(raw[:MAX_PASSWORD_BYTES], stored)
    except ValueError:  # malformed stored hash
        matches = False
    return matches and password_hash is not None and not too_long

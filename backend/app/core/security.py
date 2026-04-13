import hashlib
import hmac
import secrets


PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    return f"{PASSWORD_HASH_PREFIX}${PASSWORD_HASH_ITERATIONS}${salt}${derived.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        prefix, iterations_text, salt, stored_hash = password_hash.split("$", 3)
        if prefix != PASSWORD_HASH_PREFIX:
            return False
        iterations = int(iterations_text)
    except (TypeError, ValueError):
        return False

    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(derived.hex(), stored_hash)


def hash_sms_code(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone}:{code}".encode("utf-8")).hexdigest()


def generate_random_code(length: int = 6) -> str:
    alphabet = "0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)

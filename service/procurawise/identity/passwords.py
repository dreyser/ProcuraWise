from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id via argon2-cffi (OWASP-recommended default as of writing) - not
# passlib, which has been unmaintained since 2020 and has known friction with
# modern bcrypt releases. A single module-level hasher is safe to reuse across
# calls: PasswordHasher itself carries no mutable per-call state.
_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain)
    except VerifyMismatchError:
        return False

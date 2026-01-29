"""
Password hashing using Argon2id.

Argon2id is the recommended algorithm for password hashing,
combining Argon2i (memory-hard, side-channel resistant)
and Argon2d (faster but less side-channel resistant).
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Configure Argon2id hasher with secure defaults
# These values are tuned for typical server hardware
_hasher = PasswordHasher(
    time_cost=3,  # Number of iterations
    memory_cost=65536,  # 64 MiB memory usage
    parallelism=4,  # Number of parallel threads
    hash_len=32,  # Length of the hash in bytes
    salt_len=16,  # Length of random salt in bytes
)


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.

    Args:
        password: Plain text password to hash.

    Returns:
        Argon2id hash string (includes algorithm params and salt).
    """
    return _hasher.hash(password)


def verify_password(password: str, hash_str: str) -> bool:
    """
    Verify a password against an Argon2id hash.

    Args:
        password: Plain text password to verify.
        hash_str: Argon2id hash string to verify against.

    Returns:
        True if password matches, False otherwise.
    """
    try:
        _hasher.verify(hash_str, password)
        return True
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(hash_str: str) -> bool:
    """
    Check if a hash needs to be rehashed due to parameter changes.

    Args:
        hash_str: Argon2id hash string to check.

    Returns:
        True if hash should be regenerated with current parameters.
    """
    return _hasher.check_needs_rehash(hash_str)

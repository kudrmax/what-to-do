import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"WTD1"
SALT_SIZE = 16
IV_SIZE = 12
TAG_SIZE = 16
HEADER_SIZE = len(MAGIC) + SALT_SIZE + IV_SIZE
KEY_SIZE = 32
ITERATIONS = 600_000


class WrongPassword(Exception):
    pass


class SnapshotCipher:
    def __init__(self, password: str, salt: bytes) -> None:
        self._salt = salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=ITERATIONS,
        )
        self._key = kdf.derive(password.encode("utf-8"))
        self._aead = AESGCM(self._key)

    @staticmethod
    def new_salt() -> bytes:
        return os.urandom(SALT_SIZE)

    def encrypt(self, data: bytes) -> bytes:
        return self._seal(os.urandom(IV_SIZE), data)

    def encrypt_stable(self, data: bytes) -> bytes:
        iv = hmac.new(self._key, data, hashlib.sha256).digest()[:IV_SIZE]
        return self._seal(iv, data)

    def decrypt(self, blob: bytes) -> bytes:
        if len(blob) < HEADER_SIZE + TAG_SIZE or not blob.startswith(MAGIC):
            raise WrongPassword("not an encrypted snapshot")
        salt_end = len(MAGIC) + SALT_SIZE
        if blob[len(MAGIC):salt_end] != self._salt:
            raise WrongPassword("salt mismatch")
        iv = blob[salt_end:HEADER_SIZE]
        try:
            return self._aead.decrypt(iv, blob[HEADER_SIZE:], None)
        except InvalidTag as error:
            raise WrongPassword("wrong password") from error

    def _seal(self, iv: bytes, data: bytes) -> bytes:
        return MAGIC + self._salt + iv + self._aead.encrypt(iv, data, None)

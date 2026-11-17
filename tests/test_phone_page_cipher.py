import base64
import json
from pathlib import Path

import pytest

from where_to_go.phone_page.cipher import SnapshotCipher, WrongPassword

FIXTURES = Path(__file__).parent / "fixtures"


def test_round_trip_and_header():
    c = SnapshotCipher("pw", SnapshotCipher.new_salt())
    blob = c.encrypt(b"data")
    assert blob[:4] == b"WTD1" and len(blob) == 4 + 16 + 12 + len(b"data") + 16
    assert c.decrypt(blob) == b"data"


def test_random_iv_differs_stable_iv_repeats():
    c = SnapshotCipher("pw", SnapshotCipher.new_salt())
    assert c.encrypt(b"x") != c.encrypt(b"x")
    assert c.encrypt_stable(b"x") == c.encrypt_stable(b"x")
    assert c.encrypt_stable(b"x")[20:32] != c.encrypt_stable(b"y")[20:32]


def test_stable_blob_decrypts():
    c = SnapshotCipher("pw", SnapshotCipher.new_salt())
    assert c.decrypt(c.encrypt_stable(b"x")) == b"x"


def test_wrong_password():
    salt = SnapshotCipher.new_salt()
    with pytest.raises(WrongPassword):
        SnapshotCipher("other", salt).decrypt(SnapshotCipher("pw", salt).encrypt(b"x"))


def test_salt_mismatch():
    blob = SnapshotCipher("pw", SnapshotCipher.new_salt()).encrypt(b"x")
    with pytest.raises(WrongPassword):
        SnapshotCipher("pw", SnapshotCipher.new_salt()).decrypt(blob)


def test_malformed_blob():
    c = SnapshotCipher("pw", SnapshotCipher.new_salt())
    with pytest.raises(WrongPassword):
        c.decrypt(b"short")


def test_shared_vector_decrypts():
    v = json.loads((FIXTURES / "phone_page_vector.json").read_text())
    blob = base64.b64decode(v["blob_base64"])
    assert SnapshotCipher(v["password"], blob[4:20]).decrypt(blob).decode() == v["plaintext"]

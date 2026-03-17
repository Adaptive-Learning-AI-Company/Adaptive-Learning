from backend.config import normalize_avatar_id
from backend.profile_security import decrypt_profile_secret, encrypt_profile_secret, mask_secret


def test_profile_secret_round_trip():
    secret = "sk-test-1234567890"
    encrypted = encrypt_profile_secret(secret)

    assert encrypted is not None
    assert encrypted != secret
    assert decrypt_profile_secret(encrypted) == secret


def test_profile_secret_mask_uses_last_four_characters():
    secret = "sk-test-1234567890"
    encrypted = encrypt_profile_secret(secret)

    assert mask_secret(encrypted) == "****7890"


def test_normalize_avatar_id_rejects_unknown_values():
    assert normalize_avatar_id("schoolboy") == "schoolboy"
    assert normalize_avatar_id("SCHOOLGIRL") == "schoolgirl"
    assert normalize_avatar_id("robot") == "schoolgirl"

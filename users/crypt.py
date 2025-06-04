from cryptography.fernet import Fernet
import base64
import hashlib

def get_fernet_from_fingerprint(fingerprint: str) -> Fernet:
    """
    Derives a Fernet instance from a fingerprint string.
    """
    digest = hashlib.sha256(fingerprint.encode()).digest()  # 32 bytes
    key = base64.urlsafe_b64encode(digest)  # Fernet requires base64-encoded 32-byte key
    return Fernet(key)

def encrypt_with_fingerprint(data: dict, fingerprint: str) -> dict:
    """
    Encrypts string fields in the dictionary using fingerprint-derived Fernet key.
    """
    fernet = get_fernet_from_fingerprint(fingerprint)
    encrypted = {}
    for key, value in data.items():
        if isinstance(value, str) and value.strip():
            encrypted[key] = fernet.encrypt(value.encode()).decode()
        else:
            encrypted[key] = value
    return encrypted

def decrypt_with_fingerprint(data: dict, fingerprint: str) -> dict:
    """
    Decrypts encrypted string fields in the dictionary using fingerprint-derived Fernet key.
    """
    fernet = get_fernet_from_fingerprint(fingerprint)
    decrypted = {}
    for key, value in data.items():
        if isinstance(value, str):
            try:
                decrypted[key] = fernet.decrypt(value.encode()).decode()
            except Exception:
                decrypted[key] = value
        else:
            decrypted[key] = value
    return decrypted

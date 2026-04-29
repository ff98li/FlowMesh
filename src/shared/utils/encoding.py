import base64
import binascii


def encode_bytes_to_base64_text(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_base64_text_to_bytes(raw: str | bytes) -> bytes:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("ascii")
        return base64.b64decode(raw, validate=True)
    except (UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("Invalid base64 text payload") from exc

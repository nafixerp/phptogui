"""Legacy password crypto — byte-exact port of the GoldApp PHP algorithm.

Source of truth:
  - app/Models/UserM.php::fpCrypt()        (lines 76-96)
  - app/Services/PasswordService.php::fpCrypt()

Rules extracted from PHP:
  * Operates on the RAW BYTES of the password (PHP strlen/substr/ord are
    byte-wise, not multibyte). We therefore encode the input as UTF-8 and
    process bytes.
  * For each byte i (0-based) of the trimmed string:
        offset = (i + 1) * (length + 2)
        out_byte = (src_byte + offset) % 256      # PHP chr() wraps mod 256
    (mode 1 = encrypt = "+ offset"; mode 2 = decrypt = "- offset".)
  * A leading space (0x20) is prepended, then PHP trim() strips
    " \\t\\n\\r\\0\\x0B" from BOTH ends of the raw byte string.
  * The trimmed bytes are reinterpreted as Windows-1252 and re-encoded UTF-8
    (PHP: mb_convert_encoding($result, 'UTF-8', 'Windows-1252')). mbstring maps
    the five undefined CP1252 bytes (0x81,0x8D,0x8F,0x90,0x9D) to U+0081 etc.

Verified IDENTICAL to PHP 8.4 output across ASCII + multibyte test vectors
(see python_gui/tools/parity_check.py).

Login matches on  UPPER(HEX(pcode)) == hex(fp_encrypt(password))  — see
UserM::authenticateLegacy().
"""

from __future__ import annotations

# PHP trim() default character set.
_TRIM = b" \t\n\r\x00\x0b"

# CP1252 bytes with no assigned character; mbstring maps these to U+00XX.
_UNDEF = frozenset({0x81, 0x8D, 0x8F, 0x90, 0x9D})


def _cp1252_to_unicode(raw: bytes) -> str:
    out: list[str] = []
    for b in raw:
        out.append(chr(b) if b in _UNDEF else bytes([b]).decode("cp1252"))
    return "".join(out)


def fp_crypt(pcode: str, mode: int) -> bytes:
    """Port of UserM::fpCrypt(). mode 1 = encrypt, mode 2 = decrypt."""
    src = pcode.encode("utf-8")
    trimmed = src.strip(_TRIM)
    length = len(trimmed)

    raw = bytearray(b" ")
    for i in range(length):
        b = src[i]
        offset = (i + 1) * (length + 2)
        raw.append((b + offset) % 256 if mode == 1 else (b - offset) % 256)

    s = bytes(raw).strip(_TRIM)
    if not s:
        return b""
    return _cp1252_to_unicode(s).encode("utf-8")


def fp_encrypt(password: str) -> bytes:
    """Encrypt a plaintext password to the legacy `pcode` byte string."""
    return fp_crypt(password, 1)


def pcode_hex(password: str) -> str:
    """UPPER(HEX(pcode)) for the given plaintext — the login match key."""
    return fp_encrypt(password).hex().upper()


def pcode_value(password: str) -> str:
    """The string stored in `userm.pcode` (PasswordService::encrypt).

    PHP stores the UTF-8 text of the fp-encrypted bytes; the DB column is
    VARCHAR, and login compares UPPER(HEX(pcode)). Returning the decoded str
    lets the driver re-encode to utf8mb4 to the identical bytes.
    """
    return fp_encrypt(password).decode("utf-8")


if __name__ == "__main__":
    import sys

    for p in sys.argv[1:] or ["admin"]:
        print(f"{p}\t{pcode_hex(p)}")

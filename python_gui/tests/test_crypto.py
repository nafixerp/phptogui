"""Crypto unit tests — pinned reference vectors generated from the PHP original.

These hashes were produced by app/Models/UserM.php::fpCrypt(mode=1) on PHP 8.4
and verified via python_gui/tools/parity_check.py. They lock the algorithm so a
regression in the port can never silently break login parity.
"""

from python_gui.core.crypto import pcode_hex

# plaintext -> UPPER(HEX(pcode)) from PHP
REFERENCE = {
    "1": "34",
    "admin": "6872E2809AE280A6E28098",
    "ADMIN": "4852626571",
    "GoldShop@123": "55E280B9E28093C593E284A2C2BCC391C3A0C2BEC2BDC38CC39B",
    "password": "7A75E28098E280BAC2A9C2ABC2B8C2B4",
    "Abc12345": "4B76C28159646F7AE280A6",
    "9876543210": "45505B66717CE280A1E28099C29DC2A8",
    "x": "7B",
    "  spaced  ": "2830E280B9C290E280B0E2809C",
    "India₹": "53E2809AE2809AE28098E2809C1EC388",
}


def test_reference_vectors():
    for plain, expected in REFERENCE.items():
        assert pcode_hex(plain) == expected, plain


def test_empty_password_is_empty_hash():
    assert pcode_hex("") == ""
    assert pcode_hex("   ") == ""

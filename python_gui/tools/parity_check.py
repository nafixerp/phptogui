"""Parity proof for the legacy password crypto: Python port vs PHP original.

Runs the real PHP fpCrypt algorithm (PHP 8.x required on PATH) over a set of
plaintexts and compares UPPER(HEX(pcode)) against core.crypto.pcode_hex().

This is the Phase 1 parity proof: a Python login can only match userm rows if
its hash is byte-identical to what the Laravel app produced. Exit code 0 = all
vectors identical.

    python -m python_gui.tools.parity_check
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# Allow running both as a module and as a plain script.
try:
    from ..core.crypto import pcode_hex
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from python_gui.core.crypto import pcode_hex

VECTORS = [
    "1", "admin", "ADMIN", "GoldShop@123", "password", "Abc12345",
    "9876543210", "x", "  spaced  ", "India₹", "P@ssw0rd!", "0000",
]

_PHP = r"""<?php
function fpCrypt(string $pcode, int $mode): string {
    $trimmed = trim($pcode);
    $length = strlen($trimmed);
    $result = ' ';
    for ($i = 0; $i < $length; $i++) {
        $char = substr($pcode, $i, 1);
        $offset = ($i + 1) * ($length + 2);
        $ascii = ord($char);
        $result .= chr($mode === 1 ? $ascii + $offset : $ascii - $offset);
    }
    $result = trim($result);
    if ($result === '') return '';
    return mb_convert_encoding($result, 'UTF-8', 'Windows-1252');
}
foreach ($argv as $i => $p) {
    if ($i === 0) continue;
    echo strtoupper(bin2hex(fpCrypt($p, 1))) . "\n";
}
"""


def php_hashes(vectors: list[str]) -> list[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".php", delete=False) as f:
        f.write(_PHP)
        php_path = f.name
    out = subprocess.run(
        ["php", php_path, *vectors], capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def main() -> int:
    try:
        php = php_hashes(VECTORS)
    except FileNotFoundError:
        print("PHP not found on PATH — cannot run cross-language parity check.")
        return 2
    except subprocess.CalledProcessError as exc:
        print("PHP execution failed:", exc.stderr)
        return 2

    failures = 0
    print(f"{'plaintext':<16} {'match':<6} python==php hex")
    print("-" * 60)
    for plain, php_hex in zip(VECTORS, php):
        py_hex = pcode_hex(plain)
        ok = py_hex == php_hex
        failures += 0 if ok else 1
        print(f"{plain!r:<16} {'OK' if ok else 'FAIL':<6} {py_hex}")
        if not ok:
            print(f"{'':<16} {'':<6} php : {php_hex}")

    print("-" * 60)
    if failures:
        print(f"{failures} mismatch(es) — NOT parity-safe.")
        return 1
    print(f"All {len(VECTORS)} vectors identical — crypto is parity-safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

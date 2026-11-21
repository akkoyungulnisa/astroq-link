"""Unit tests for PQCFileVault encryption, 1-byte tamper detection & atomic rollback."""

from pathlib import Path
import pytest

from astroq_link.core import IntegrityTamperError
from astroq_link.crypto import PQCFileVault


def test_encrypt_and_decrypt_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "telemetry.txt"
    enc = tmp_path / "telemetry.pqc"
    dst = tmp_path / "restored.txt"

    original_text = "APO_ALT:2000m | QBER:0.018 | STATUS:NOMINAL\n" * 10
    src.write_text(original_text, encoding="utf-8")

    vault = PQCFileVault(passphrase="KuantumGuvenliTest2026!")
    seal = vault.encrypt_file(src, enc)

    assert len(seal) == 64
    assert enc.exists()
    assert vault.decrypt_and_verify(enc, dst) is True
    assert dst.read_text(encoding="utf-8") == original_text


def test_single_byte_tamper_detection_blocks_decryption(tmp_path: Path) -> None:
    src = tmp_path / "mission.bin"
    enc = tmp_path / "mission.pqc"
    dst = tmp_path / "restored.bin"

    src.write_bytes(b"CRITICAL_FLIGHT_DATA_BLOCK_" * 12)
    vault = PQCFileVault(passphrase="GizliUcusAnahtari")
    vault.encrypt_file(src, enc)

    # Şifreli dosyanın ortasındaki 1 baytı kurcala (Bit-Flip saldırısı)
    tampered = bytearray(enc.read_bytes())
    tampered[len(tampered) // 2] ^= 0xFF
    enc.write_bytes(bytes(tampered))

    with pytest.raises(IntegrityTamperError):
        vault.decrypt_and_verify(enc, dst)

    # Bozuk veri diske kesinlikle yazılmamış olmalı
    assert not dst.exists()


def test_wrong_passphrase_rejected(tmp_path: Path) -> None:
    src = tmp_path / "secret.txt"
    enc = tmp_path / "secret.pqc"
    dst = tmp_path / "out.txt"

    src.write_text("Sadece yetkili yer istasyonu okuyabilir.", encoding="utf-8")
    PQCFileVault("DogruParola").encrypt_file(src, enc)

    with pytest.raises(IntegrityTamperError):
        PQCFileVault("YanlisParola").decrypt_and_verify(enc, dst)


def test_atomic_rollback_on_midstream_io_fault(tmp_path: Path) -> None:
    src = tmp_path / "large_log.txt"
    enc = tmp_path / "incomplete.pqc"

    # En az 4 blok (4 * 64 = 256 bayt) oluşturacak veri yaz
    src.write_bytes(b"A" * 300)
    vault = PQCFileVault("RollbackTestKey")

    with pytest.raises(OSError):
        vault.encrypt_file(src, enc, simulate_io_fault_at_block=2)

    # Atomik rollback sonrası yarım kalmış şifreli dosya bırakılmamalı
    assert not enc.exists()


def test_empty_file_encryption_and_verification(tmp_path: Path) -> None:
    src = tmp_path / "empty.txt"
    enc = tmp_path / "empty.pqc"
    dst = tmp_path / "empty_restored.txt"

    src.write_bytes(b"")
    vault = PQCFileVault("EmptyFileKey")
    vault.encrypt_file(src, enc)

    assert vault.decrypt_and_verify(enc, dst) is True
    assert dst.read_bytes() == b""

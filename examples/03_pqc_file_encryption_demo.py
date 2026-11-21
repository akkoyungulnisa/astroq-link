"""Demo 3: Real file encryption, circular seal verification & bit-flip test."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from astroq_link.core import IntegrityTamperError
from astroq_link.crypto import PQCFileVault


def run_demo() -> None:
    sample_csv = ROOT_DIR / "data" / "sample_telemetry.csv"
    encrypted_pqc = ROOT_DIR / "data" / "sample_telemetry.pqc"
    restored_csv = ROOT_DIR / "data" / "sample_telemetry_restored.csv"

    vault = PQCFileVault(passphrase="KuantumGuvenliDosyaKasasi2026!")

    print("🔐 AstroQ-Link: Post-Quantum Dairesel Dosya Şifreleme ve Kurcalama Testi")
    print("=" * 84)

    # 1. Şifreleme
    seal = vault.encrypt_file(sample_csv, encrypted_pqc)
    print(f"1. Şifreleme Tamamlandı -> {encrypted_pqc.name}")
    print(f"   Dairesel Kapanış Mührü (Tail -> Head): {seal[:32]}...")

    # 2. Temiz Doğrulama ve Deşifreleme
    if vault.decrypt_and_verify(encrypted_pqc, restored_csv):
        print(f"2. Bütünlük Doğrulandı  -> Orijinal veri eksiksiz çözüldü: {restored_csv.name}")

    # 3. 1-Bayt Kurcalama (Bit-Flip) Saldırısı Simülasyonu
    tampered_bytes = bytearray(encrypted_pqc.read_bytes())
    target_offset = len(tampered_bytes) // 2
    tampered_bytes[target_offset] ^= 0xFF
    encrypted_pqc.write_bytes(bytes(tampered_bytes))
    print(f"3. Saldırı Enjeksiyonu  -> {target_offset}. baytta 1-bayt Bit-Flip uygulandı!")

    corrupted_out = ROOT_DIR / "data" / "corrupted_output.csv"
    try:
        vault.decrypt_and_verify(encrypted_pqc, corrupted_out)
    except IntegrityTamperError as exc:
        print(f"4. Savunma Tepkisi      -> [ENGELLENDİ] {exc}")
        print(f"   Diske Bozuk Veri Yazıldı mı? : {corrupted_out.exists()}")

    # Demo geçici dosyalarını temizle
    for tmp in (encrypted_pqc, restored_csv, corrupted_out):
        if tmp.exists():
            tmp.unlink()

    print("=" * 84)


if __name__ == "__main__":
    run_demo()

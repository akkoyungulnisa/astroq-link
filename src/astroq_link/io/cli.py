"""Command-line interface (argparse) for encrypt, decrypt, and simulate commands."""

import argparse
from pathlib import Path
import sys
from typing import Optional, Sequence

from astroq_link.core import IntegrityTamperError
from astroq_link.crypto import PQCFileVault
from astroq_link.engine import TelemetryRouter
from .csv_exporter import TelemetryExporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astroq-link",
        description="AstroQ-Link: Zero-Dependency Circular DLL, LIFO Stack & PQC Vault CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. encrypt alt komutu
    enc_parser = subparsers.add_parser("encrypt", help="Dosyayı PQC dairesel zincirle şifreler.")
    enc_parser.add_argument("input_file", type=Path, help="Şifrelenecek kaynak dosya yolu")
    enc_parser.add_argument("output_file", type=Path, help="Çıktı .pqc dosya yolu")
    enc_parser.add_argument("-p", "--passphrase", required=True, help="PQC oturum parolası")

    # 2. decrypt alt komutu
    dec_parser = subparsers.add_parser("decrypt", help="Şifreli dosyayı doğrular ve geri çözer.")
    dec_parser.add_argument("input_file", type=Path, help="Şifreli .pqc dosya yolu")
    dec_parser.add_argument("output_file", type=Path, help="Çözülen çıktı dosya yolu")
    dec_parser.add_argument("-p", "--passphrase", required=True, help="PQC oturum parolası")

    # 3. simulate alt komutu
    sim_parser = subparsers.add_parser("simulate", help="2000m uçuş ve kesinti simülasyonu çalıştırır.")
    sim_parser.add_argument("--altitude", type=float, default=2000.0, help="Hedef tepe irtifası (m)")
    sim_parser.add_argument("--export-csv", type=Path, default=None, help="Yer istasyonu CSV çıktı yolu")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "encrypt":
        if not args.input_file.exists():
            print(f"[HATA] Kaynak dosya bulunamadı: {args.input_file}", file=sys.stderr)
            return 1
        vault = PQCFileVault(args.passphrase)
        seal = vault.encrypt_file(args.input_file, args.output_file)
        print(f"[OK] Şifrelendi -> {args.output_file} | Dairesel Mühür: {seal[:24]}...")
        return 0

    if args.command == "decrypt":
        if not args.input_file.exists():
            print(f"[HATA] Şifreli dosya bulunamadı: {args.input_file}", file=sys.stderr)
            return 1
        vault = PQCFileVault(args.passphrase)
        try:
            vault.decrypt_and_verify(args.input_file, args.output_file)
            print(f"[OK] Bütünlük doğrulandı ve geri çözüldü -> {args.output_file}")
            return 0
        except IntegrityTamperError as exc:
            print(f"[GÜVENLİK İHLALİ] {exc}", file=sys.stderr)
            return 2

    if args.command == "simulate":
        router = TelemetryRouter()
        stats = router.simulate_ascent_mission(target_altitude=args.altitude)
        print(
            f"[SİMÜLASYON TAMAMLANDI] İrtifa={args.altitude}m | Üretilen={stats.total_generated} | "
            f"Stack Kurtarma={stats.recovered_from_stack} | Kanal Değişimi={stats.link_switches}"
        )
        if args.export_csv is not None:
            count = TelemetryExporter.export_telemetry_csv(router.ground_station_log, args.export_csv)
            print(f"[CSV] {count} doğrulanmış paket kaydedildi -> {args.export_csv}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

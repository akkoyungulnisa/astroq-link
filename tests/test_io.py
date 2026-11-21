"""Unit tests for TelemetryExporter and CLI interface."""

import csv
import json
from pathlib import Path

from astroq_link.core import CircularDoublyLinkedList, QuantumTelemetryPacket
from astroq_link.io import TelemetryExporter, main


def test_csv_and_json_exporter(tmp_path: Path) -> None:
    ring: CircularDoublyLinkedList[QuantumTelemetryPacket] = CircularDoublyLinkedList()
    ring.append(QuantumTelemetryPacket(1, 500.0, 110.0, 954.6, 0.02, False, "NOMINAL"))
    ring.append(QuantumTelemetryPacket(2, 1920.0, 32.0, 802.5, 0.04, True, "RF_BLACKOUT"))

    csv_file = tmp_path / "ground_log.csv"
    json_file = tmp_path / "ground_log.json"

    assert TelemetryExporter.export_telemetry_csv(ring, csv_file) == 2
    assert TelemetryExporter.export_telemetry_json(ring, json_file) == 2

    with csv_file.open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "packet_id"
    assert len(rows) == 3
    assert rows[2][6] == "RF_BLACKOUT"

    parsed_json = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(parsed_json) == 2
    assert parsed_json[1]["altitude_m"] == 1920.0


def test_cli_encrypt_decrypt_and_tamper_exit_codes(tmp_path: Path) -> None:
    src = tmp_path / "flight.txt"
    enc = tmp_path / "flight.pqc"
    dst = tmp_path / "flight_out.txt"
    src.write_text("TELEMETRY_PAYLOAD_2026", encoding="utf-8")

    # 1. CLI üzerinden şifreleme
    rc_enc = main(["encrypt", str(src), str(enc), "-p", "CliTestKey2026"])
    assert rc_enc == 0
    assert enc.exists()

    # 2. CLI üzerinden temiz deşifreleme
    rc_dec = main(["decrypt", str(enc), str(dst), "-p", "CliTestKey2026"])
    assert rc_dec == 0
    assert dst.read_text(encoding="utf-8") == "TELEMETRY_PAYLOAD_2026"

    # 3. Dosyayı kurcalayıp CLI çıkış kodunun 2 (GÜVENLİK İHLALİ) olduğunu doğrula
    tampered = bytearray(enc.read_bytes())
    tampered[-1] ^= 0xFF
    enc.write_bytes(bytes(tampered))

    rc_tamper = main(["decrypt", str(enc), str(tmp_path / "bad.txt"), "-p", "CliTestKey2026"])
    assert rc_tamper == 2


def test_cli_simulate_with_csv_export(tmp_path: Path) -> None:
    out_csv = tmp_path / "sim_out.csv"
    rc = main(["simulate", "--altitude", "2000", "--export-csv", str(out_csv)])
    assert rc == 0
    assert out_csv.exists()
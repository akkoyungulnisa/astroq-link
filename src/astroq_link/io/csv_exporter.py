"""Ground station verified telemetry CSV/JSON logger."""

import csv
import json
from pathlib import Path

from astroq_link.core import (
    CircularDoublyLinkedList,
    QuantumTelemetryPacket,
    SecurityIncident,
)


class TelemetryExporter:
    """
    Yer istasyonu dairesel günlüğündeki (CircularDoublyLinkedList) doğrulanmış
    telemetri paketlerini ve güvenlik olaylarını CSV/JSON formatında dışa aktarır.
    """

    TELEMETRY_HEADERS: tuple[str, ...] = (
        "packet_id",
        "altitude_m",
        "velocity_ms",
        "pressure_hpa",
        "qber",
        "is_critical",
        "status",
    )

    @classmethod
    def export_telemetry_csv(
        cls,
        packet_ring: CircularDoublyLinkedList[QuantumTelemetryPacket],
        output_path: str | Path,
    ) -> int:
        """Dairesel listedeki paketleri yerleşik list'e çevirmeden doğrudan CSV'ye yazar."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        written = 0

        with out_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(cls.TELEMETRY_HEADERS)
            for pkt in packet_ring:
                writer.writerow(
                    [
                        pkt.packet_id,
                        pkt.altitude_m,
                        pkt.velocity_ms,
                        pkt.pressure_hpa,
                        pkt.qber,
                        pkt.is_critical,
                        pkt.status,
                    ]
                )
                written += 1

        return written

    @staticmethod
    def export_telemetry_json(
        packet_ring: CircularDoublyLinkedList[QuantumTelemetryPacket],
        output_path: str | Path,
    ) -> int:
        """Doğrulanmış telemetri akışını yapılandırılmış JSON dosyasına aktarır."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        records = [
            {
                "packet_id": pkt.packet_id,
                "altitude_m": pkt.altitude_m,
                "velocity_ms": pkt.velocity_ms,
                "pressure_hpa": pkt.pressure_hpa,
                "qber": pkt.qber,
                "is_critical": pkt.is_critical,
                "status": pkt.status,
            }
            for pkt in packet_ring
        ]

        out_file.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        return len(records)

    @staticmethod
    def export_incidents_csv(
        incidents: list[SecurityIncident],
        output_path: str | Path,
    ) -> int:
        """SOC güvenlik ihlali kayıtlarını denetim (audit) CSV dosyasına yazar."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        with out_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(("tick", "severity", "description"))
            for inc in incidents:
                writer.writerow((inc.tick, inc.severity, inc.description))

        return len(incidents)
"""Autonomous offline key ratcheting and SOC alert prioritization under cyber-attack."""

from dataclasses import dataclass
import hashlib
from typing import Optional

from astroq_link.core import (
    CircularDoublyLinkedList,
    CriticalLIFOStack,
    SecurityIncident,
)
from astroq_link.crypto import secure_zero_bytearray


class _KeySlot:
    """Dairesel anahtar halkasındaki değiştirilebilir anahtar yuvası (Zeroization destekli)."""
    __slots__ = ("slot_id", "key_buffer")

    def __init__(self, slot_id: int, initial_key: bytes) -> None:
        self.slot_id: int = slot_id
        self.key_buffer: bytearray = bytearray(initial_key)


@dataclass
class ShieldStats:
    frames_processed: int = 0
    offline_frames: int = 0
    attacks_blocked: int = 0
    rollbacks_executed: int = 0
    soc_alerts_flushed: int = 0


class AutonomousEdgeShield:
    """
    İnternet/KMS bağlantısı kesildiğinde merkez sunucuya ihtiyaç duymadan
    CircularDoublyLinkedList üzerinde anahtar döndüren (Offline Forward Secrecy),
    yerel veri kurcalamalarını CriticalLIFOStack ile geri alan ve bağlantı
    döndüğünde en güncel güvenlik ihlalini SOC merkezine ilk sırada ileten motor.
    """

    def __init__(self, passphrase: str, ring_slots: int = 4, alert_capacity: int = 64) -> None:
        if ring_slots < 2:
            raise ValueError("Anahtar döndürme halkası en az 2 slot içermelidir.")

        seed = hashlib.sha3_256(passphrase.encode("utf-8")).digest()
        self.key_ring: CircularDoublyLinkedList[_KeySlot] = CircularDoublyLinkedList(
            max_capacity=ring_slots, overwrite_on_full=False
        )

        curr_seed = seed
        for i in range(ring_slots):
            curr_seed = hashlib.sha3_256(curr_seed + i.to_bytes(2, "big")).digest()
            self.key_ring.append(_KeySlot(slot_id=i, initial_key=curr_seed))

        self.rollback_stack: CriticalLIFOStack[tuple[int, bytes]] = CriticalLIFOStack()
        self.soc_alert_stack: CriticalLIFOStack[SecurityIncident] = CriticalLIFOStack(
            max_capacity=alert_capacity
        )
        self.last_valid_seal: str = hashlib.sha3_256(seed).hexdigest()
        self.stats = ShieldStats()

    def _ratchet_next_key(self) -> tuple[int, bytes]:
        """
        Halkada bir adım ilerler (O(1)), SHAKE-256 ile yeni oturum anahtarı türetir
        ve bir önceki slotun belleğini sıfırlarla ezer (Forward Secrecy).
        """
        prev_node = self.key_ring.get_head()
        assert prev_node is not None
        prev_key_copy = bytes(prev_node.data.key_buffer)

        # Önceki slotun anahtarını RAM'de sıfırla
        secure_zero_bytearray(prev_node.data.key_buffer)

        # Halkada saat yönünde bir sonraki slota geç
        curr_node = self.key_ring.rotate_forward()
        assert curr_node is not None

        sponge = hashlib.shake_256()
        sponge.update(prev_key_copy)
        sponge.update(bytes(curr_node.data.key_buffer))
        sponge.update(self.last_valid_seal.encode("utf-8"))
        new_key = sponge.digest(32)

        curr_node.data.key_buffer[:] = new_key
        return curr_node.data.slot_id, new_key

    def process_frame(
        self,
        tick: int,
        payload: bytes,
        internet_online: bool = True,
        simulate_tamper: bool = False,
    ) -> dict[str, object]:
        """
        Veri çerçevesini çevrimdışı/çevrimiçi modda mühürler ve bütünlüğünü doğrular.
        Kurcalama tespit edilirse işlemi LIFO yığınından geri sarar.
        """
        self.stats.frames_processed += 1
        if not internet_online:
            self.stats.offline_frames += 1

        slot_id, active_key = self._ratchet_next_key()
        encrypted = bytes(b ^ active_key[i % len(active_key)] for i, b in enumerate(payload))
        expected_seal = hashlib.sha3_256(
            f"{self.last_valid_seal}:{encrypted.hex()}".encode("utf-8")
        ).hexdigest()

        self.rollback_stack.push((tick, encrypted))

        # Saldırı enjeksiyonu: bellekteki şifreli verinin 1 baytını boz
        if simulate_tamper and len(encrypted) > 0:
            corrupted = bytearray(encrypted)
            corrupted[0] ^= 0xFF
            encrypted = bytes(corrupted)

        actual_seal = hashlib.sha3_256(
            f"{self.last_valid_seal}:{encrypted.hex()}".encode("utf-8")
        ).hexdigest()

        if actual_seal != expected_seal:
            # Müdahale yakalandı -> LIFO Rollback
            reverted_tick, _ = self.rollback_stack.pop()
            self.stats.attacks_blocked += 1
            self.stats.rollbacks_executed += 1

            incident = SecurityIncident(
                tick=tick,
                severity="CRITICAL_TAMPER",
                description=f"T={reverted_tick} anında 1-bayt müdahale engellendi ve geri alındı.",
            )
            if not self.soc_alert_stack.is_full():
                self.soc_alert_stack.push(incident)

            return {
                "tick": tick,
                "status": "TAMPER_BLOCKED",
                "mode": "ONLINE" if internet_online else "OFFLINE",
                "slot_id": slot_id,
                "flushed_alerts": [],
            }

        self.last_valid_seal = actual_seal
        flushed: list[SecurityIncident] = []

        # İnternet bağlantısı aktifse biriken en güncel kritik alarmları LIFO sırasıyla SOC'a bas
        if internet_online and not self.soc_alert_stack.is_empty():
            while not self.soc_alert_stack.is_empty():
                alert: Optional[SecurityIncident] = self.soc_alert_stack.pop_safe()
                if alert is not None:
                    flushed.append(alert)
                    self.stats.soc_alerts_flushed += 1

        return {
            "tick": tick,
            "status": "SEALED_OK",
            "mode": "ONLINE" if internet_online else "OFFLINE",
            "slot_id": slot_id,
            "seal": actual_seal,
            "flushed_alerts": flushed,
        }
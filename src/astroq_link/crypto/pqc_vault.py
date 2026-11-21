"""PQCFileVault with circular block sealing, memory zeroization, and tamper detection."""

import hashlib
from pathlib import Path
from typing import Optional

from astroq_link.core import (
    CipherBlock,
    CircularDoublyLinkedList,
    CriticalLIFOStack,
    IntegrityTamperError,
    RollbackAction,
)
from .lattice_kdf import LatticeKeyDeriver, secure_zero_bytearray


class PQCFileVault:
    """
    Dosyaları sabit boyutlu parçalara bölerek Çift Yönlü Dairesel Bağlı Liste
    üzerinde kümülatif kriptografik zincirle birbirine kilitleyen ve hata/saldırı
    anında LIFO Stack ile atomik geri alma (rollback) uygulayan PQC veri kasası.
    """

    CHUNK_SIZE: int = 64
    SEAL_BYTES: int = 32  # SHA3-256 dairesel mühür boyutu

    def __init__(self, passphrase: str) -> None:
        self._kdf = LatticeKeyDeriver(passphrase)

    @staticmethod
    def _xor_with_zeroization(data: bytes, keystream: bytearray) -> bytes:
        result = bytes(d ^ k for d, k in zip(data, keystream))
        secure_zero_bytearray(keystream)  # Kullanılan anahtar akışını anında RAM'den sil
        return result

    def _compute_circular_seal(self, ring: CircularDoublyLinkedList[CipherBlock]) -> str:
        """
        Çift yönlü dairesel bağlantıyı (head.prev -> tail) kullanarak
        son düğümün kümülatif MAC değerini ilk düğümün özetiyle kilitler.
        """
        head_node = ring.get_head()
        assert head_node is not None and head_node.prev is not None
        tail_node = head_node.prev
        seal_input = f"{tail_node.data.chained_mac}:{head_node.data.block_hash}".encode("utf-8")
        return hashlib.sha3_256(seal_input).hexdigest()

    def encrypt_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        simulate_io_fault_at_block: Optional[int] = None,
    ) -> str:
        """
        Dosyayı kümülatif dairesel zincirle şifreler. İşlem ortasında I/O hatası oluşursa
        CriticalLIFOStack üzerinden tamamlanan adımları geri sarıp yarım dosyayı temizler.
        """
        in_file = Path(input_path)
        out_file = Path(output_path)
        raw_data = in_file.read_bytes()

        ring: CircularDoublyLinkedList[CipherBlock] = CircularDoublyLinkedList()
        rollback_stack: CriticalLIFOStack[RollbackAction] = CriticalLIFOStack()

        prev_mac = hashlib.sha3_256(self._kdf.master_seed).hexdigest()
        total_len = len(raw_data)

        try:
            idx = 0
            offset = 0
            while True:
                if simulate_io_fault_at_block is not None and idx == simulate_io_fault_at_block:
                    raise OSError(f"Simüle edilmiş disk kesintisi (Blok #{idx}).")

                chunk = raw_data[offset : offset + self.CHUNK_SIZE]
                keystream = self._kdf.derive_block_keystream(idx, prev_mac, len(chunk))
                encrypted_chunk = self._xor_with_zeroization(chunk, keystream)

                curr_hash = hashlib.sha3_256(encrypted_chunk).hexdigest()
                # Kümülatif zincirleme: her düğüm kendinden önceki TÜM düğümlerin özetini taşır
                chained_mac = hashlib.sha3_256(f"{prev_mac}:{curr_hash}".encode("utf-8")).hexdigest()

                block = CipherBlock(
                    index=idx,
                    payload=encrypted_chunk,
                    block_hash=curr_hash,
                    chained_mac=chained_mac,
                )
                ring.append(block)
                rollback_stack.push(RollbackAction(idx, "ENCRYPT_CHUNK", curr_hash))

                prev_mac = chained_mac
                offset += self.CHUNK_SIZE
                idx += 1

                if offset >= total_len:
                    break

            circular_seal = self._compute_circular_seal(ring)

            with out_file.open("wb") as f:
                f.write(bytes.fromhex(circular_seal))
                for blk in ring:
                    f.write(blk.payload)

            return circular_seal

        except Exception:
            # Atomik Geri Alma (LIFO Rollback): Uygulanan adımları ters sırayla geri sar
            while not rollback_stack.is_empty():
                rollback_stack.pop()
            if out_file.exists():
                out_file.unlink()
            raise

    def decrypt_and_verify(self, encrypted_path: str | Path, restored_path: str | Path) -> bool:
        """
        Dairesel bütünlük mührünü doğrular; 1-bit dahi kurcalama varsa IntegrityTamperError fırlatır
        ve hedef diske bozuk veri yazmaz.
        """
        enc_file = Path(encrypted_path)
        out_file = Path(restored_path)
        file_bytes = enc_file.read_bytes()

        if len(file_bytes) < self.SEAL_BYTES:
            raise IntegrityTamperError("Şifreli dosya başlığı bozuk veya eksik (32 bayttan kısa).")

        stored_seal = file_bytes[: self.SEAL_BYTES].hex()
        ciphertext = file_bytes[self.SEAL_BYTES :]

        ring: CircularDoublyLinkedList[CipherBlock] = CircularDoublyLinkedList()
        prev_mac = hashlib.sha3_256(self._kdf.master_seed).hexdigest()
        total_len = len(ciphertext)

        idx = 0
        offset = 0
        while True:
            enc_chunk = ciphertext[offset : offset + self.CHUNK_SIZE]
            curr_hash = hashlib.sha3_256(enc_chunk).hexdigest()
            chained_mac = hashlib.sha3_256(f"{prev_mac}:{curr_hash}".encode("utf-8")).hexdigest()

            ring.append(CipherBlock(idx, enc_chunk, curr_hash, chained_mac))
            prev_mac = chained_mac
            offset += self.CHUNK_SIZE
            idx += 1

            if offset >= total_len:
                break

        recomputed_seal = self._compute_circular_seal(ring)
        if recomputed_seal != stored_seal:
            raise IntegrityTamperError(
                "Dairesel bütünlük mührü uyuşmadı! Dosya kurcalanmış veya anahtar hatalı."
            )

        rollback_stack: CriticalLIFOStack[RollbackAction] = CriticalLIFOStack()
        restored_buffer = bytearray()
        prev_mac = hashlib.sha3_256(self._kdf.master_seed).hexdigest()

        try:
            for blk in ring:
                keystream = self._kdf.derive_block_keystream(blk.index, prev_mac, len(blk.payload))
                plain_chunk = self._xor_with_zeroization(blk.payload, keystream)
                restored_buffer.extend(plain_chunk)

                rollback_stack.push(RollbackAction(blk.index, "DECRYPT_CHUNK", blk.block_hash))
                prev_mac = blk.chained_mac

            out_file.write_bytes(bytes(restored_buffer))
            return True

        except Exception:
            while not rollback_stack.is_empty():
                rollback_stack.pop()
            if out_file.exists():
                out_file.unlink()
            raise

    @staticmethod
    def compute_avalanche_ratio(cipher_a: bytes, cipher_b: bytes) -> float:
        """İki şifreli çıktı arasındaki bit değişim yüzdesini (Avalanche Effect) hesaplar."""
        min_len = min(len(cipher_a), len(cipher_b))
        if min_len == 0:
            return 0.0
        diff_bits = sum((a ^ b).bit_count() for a, b in zip(cipher_a[:min_len], cipher_b[:min_len]))
        total_bits = min_len * 8
        return round((diff_bits / total_bits) * 100.0, 2)
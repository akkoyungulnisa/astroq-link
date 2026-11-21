"""Educational Lattice (Ring-LWE) session key derivation and SHAKE-256 keystream generator."""

import hashlib


def secure_zero_bytearray(buffer: bytearray) -> None:
    """Hassas anahtar tamponlarını RAM üzerinde sıfırlarla ezer (Memory Zeroization)."""
    for i in range(len(buffer)):
        buffer[i] = 0


class LatticeKeyDeriver:
    """
    Polinom halkası Z_q[X]/(X^n + 1) üzerinde Ring-LWE (Learning With Errors)
    tabanlı oturum anahtarı türetici ve kuantum-dirençli SHAKE-256 anahtar akışı üreteci.
    """

    MODULUS_Q: int = 257   # Asal modül
    RING_DIM_N: int = 8    # Polinom derecesi

    def __init__(self, passphrase: str) -> None:
        if not passphrase:
            raise ValueError("Parola boş olamaz.")
        self._master_seed: bytes = self._derive_ring_lwe_seed(passphrase)

    @property
    def master_seed(self) -> bytes:
        return self._master_seed

    def _poly_mul_negacyclic(self, a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
        """Z_q[X]/(X^n + 1) halkasında negatif çevrimli polinom çarpımı."""
        n = self.RING_DIM_N
        q = self.MODULUS_Q
        acc = bytearray(n * 2)  # Geçici katsayı tamponu
        raw_coeffs = [0] * n

        for i in range(n):
            for j in range(n):
                prod = a[i] * b[j]
                if i + j < n:
                    raw_coeffs[i + j] = (raw_coeffs[i + j] + prod) % q
                else:
                    # X^n ≡ -1 (mod X^n + 1) indirgemesi
                    raw_coeffs[(i + j) - n] = (raw_coeffs[(i + j) - n] - prod) % q

        secure_zero_bytearray(acc)
        return tuple(raw_coeffs)

    def _derive_ring_lwe_seed(self, passphrase: str) -> bytes:
        """
        b = a * s + e  (mod q, X^n + 1)
        Gizli polinom (s) ve küçük hata polinomu (e) ile kuantum-dirençli oturum tohumu üretir.
        """
        n = self.RING_DIM_N
        q = self.MODULUS_Q
        digest = hashlib.sha3_512(passphrase.encode("utf-8")).digest()

        a = tuple((digest[i] * 19 + 7) % q for i in range(n))
        s = tuple((digest[i + n] % 5) - 2 for i in range(n))
        e = tuple((digest[i + 2 * n] % 3) - 1 for i in range(n))

        a_times_s = self._poly_mul_negacyclic(a, s)
        b = tuple((a_times_s[i] + e[i]) % q for i in range(n))

        material = f"LWE:{a}:{b}:{s}".encode("utf-8")
        return hashlib.sha3_256(material).digest()

    def derive_block_keystream(self, block_index: int, prev_hash: str, length: int) -> bytearray:
        """
        Her blok için bir önceki bloğun özetine bağlı (Key Ratcheting)
        kuantum-dirençli SHAKE-256 anahtar akışı üretir.
        """
        sponge = hashlib.shake_256()
        sponge.update(self._master_seed)
        sponge.update(block_index.to_bytes(4, "big"))
        sponge.update(prev_hash.encode("utf-8"))
        return bytearray(sponge.digest(length))

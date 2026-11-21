"""Custom domain exceptions for No-Cloning, Stack bounds, and Tamper detection."""


class AstroQError(Exception):
    """AstroQ-Link çekirdek sistemi için temel istisna sınıfı."""


class NoCloningViolationError(AstroQError):
    """Kuantum kopyalanamazlık (No-Cloning) kuralı ihlal edildiğinde fırlatılır."""


class StackOverflowError(AstroQError):
    """Kritik LIFO yığını maksimum kapasitesine ulaştığında fırlatılır."""


class StackUnderflowError(AstroQError):
    """Boş bir yığından eleman çekilmeye (pop) çalışıldığında fırlatılır."""


class RingBufferOverflowError(AstroQError):
    """Üzerine yazma (overwrite) kapalıyken dairesel tampon dolduğunda fırlatılır."""


class IntegrityTamperError(AstroQError):
    """Dairesel kriptografik mühür veya blok bütünlüğü bozulduğunda fırlatılır.""""""Custom domain exceptions for No-Cloning, Stack bounds, and Tamper detection."""

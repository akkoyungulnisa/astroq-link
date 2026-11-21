"""O(1) LIFO Stack for blackout recovery and atomic rollback."""

from typing import Generic, Iterator, Optional, TypeVar
from .exceptions import StackOverflowError, StackUnderflowError
from .nodes import StackNode

T = TypeVar("T")


class CriticalLIFOStack(Generic[T]):
    """
    Sinyal kesintisi kurtarma ve atomik işlem geri alma (Rollback) için
    sıfırdan yazılmış O(1) LIFO Yığın yapısı.
    """

    def __init__(self, max_capacity: Optional[int] = None) -> None:
        if max_capacity is not None and max_capacity <= 0:
            raise ValueError("max_capacity pozitif bir tam sayı olmalıdır.")
        self._top: Optional[StackNode[T]] = None
        self._size: int = 0
        self._max_capacity: Optional[int] = max_capacity

    @property
    def size(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    def is_full(self) -> bool:
        return self._max_capacity is not None and self._size >= self._max_capacity

    def push(self, data: T) -> None:
        """Yığının tepesine O(1) sürede yeni eleman ekler."""
        if self.is_full():
            raise StackOverflowError(
                f"Yığın maksimum kapasiteye ({self._max_capacity}) ulaştı."
            )
        new_node = StackNode(data)
        new_node.next = self._top
        self._top = new_node
        self._size += 1

    def pop(self) -> T:
        """Yığının tepesindeki en güncel elemanı O(1) sürede çıkarır."""
        if self._top is None:
            raise StackUnderflowError("Boş yığından eleman çekilemez (Stack Underflow).")
        popped_node = self._top
        self._top = popped_node.next
        popped_node.next = None
        self._size -= 1
        return popped_node.data

    def pop_safe(self) -> Optional[T]:
        """İstisna fırlatmadan pop yapar; yığın boşsa None döner."""
        if self.is_empty():
            return None
        return self.pop()

    def peek(self) -> Optional[T]:
        """Elemanı çıkarmadan yığının tepesindeki veriyi okur (O(1))."""
        return self._top.data if self._top is not None else None

    def clear(self) -> None:
        """Tüm işaretçileri çözerek yığını güvenli şekilde sıfırlar."""
        curr = self._top
        while curr is not None:
            nxt = curr.next
            curr.next = None
            curr = nxt
        self._top = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[T]:
        """Tepeden tabana doğru generator ile gezinme."""
        curr = self._top
        while curr is not None:
            yield curr.data
            curr = curr.next

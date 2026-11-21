"""O(1) Circular Doubly Linked List implementation without built-in list/deque."""

from typing import Generic, Iterator, Optional, TypeVar
from .exceptions import RingBufferOverflowError
from .nodes import DoublyNode

T = TypeVar("T")


class CircularDoublyLinkedList(Generic[T]):
    """
    Sabit bellekli Ring Buffer ve dairesel kriptografik zincirleme destekli
    sıfırdan yazılmış Çift Yönlü Dairesel Bağlı Liste.
    """

    def __init__(self, max_capacity: Optional[int] = None, overwrite_on_full: bool = True) -> None:
        if max_capacity is not None and max_capacity <= 0:
            raise ValueError("max_capacity pozitif bir tam sayı olmalıdır.")
        self._head: Optional[DoublyNode[T]] = None
        self._size: int = 0
        self._max_capacity: Optional[int] = max_capacity
        self._overwrite_on_full: bool = overwrite_on_full

    @property
    def size(self) -> int:
        return self._size

    @property
    def max_capacity(self) -> Optional[int]:
        return self._max_capacity

    def is_empty(self) -> bool:
        return self._size == 0

    def is_full(self) -> bool:
        return self._max_capacity is not None and self._size >= self._max_capacity

    def append(self, data: T) -> DoublyNode[T]:
        """Halkanın sonuna O(1) sürede yeni düğüm ekler; doluysa en eski düğümün üzerine yazar."""
        if self.is_full():
            if not self._overwrite_on_full:
                raise RingBufferOverflowError("Dairesel tampon kapasitesi doldu.")
            assert self._head is not None
            # En eski düğümün (head) verisini ez ve işaretçiyi bir adım kaydır (O(1))
            self._head.data = data
            written_node = self._head
            self._head = self._head.next
            return written_node

        new_node = DoublyNode(data)
        if self._head is None:
            new_node.next = new_node
            new_node.prev = new_node
            self._head = new_node
        else:
            tail = self._head.prev
            assert tail is not None
            tail.next = new_node
            new_node.prev = tail
            new_node.next = self._head
            self._head.prev = new_node

        self._size += 1
        return new_node

    def remove_node(self, node: DoublyNode[T]) -> T:
        """Verilen düğümü O(1) işaretçi güncellemesiyle halkadan çıkarır."""
        if self._head is None:
            raise ValueError("Boş listeden düğüm silinemez.")

        removed_data = node.data
        if self._size == 1:
            self._head = None
        else:
            assert node.prev is not None and node.next is not None
            node.prev.next = node.next
            node.next.prev = node.prev
            if node is self._head:
                self._head = node.next

        # Bellek sızıntısını (dangling reference) önlemek için işaretçileri temizle
        node.prev = None
        node.next = None
        self._size -= 1
        return removed_data

    def get_head(self) -> Optional[DoublyNode[T]]:
        return self._head

    def get_tail(self) -> Optional[DoublyNode[T]]:
        return self._head.prev if self._head is not None else None

    def rotate_forward(self) -> Optional[DoublyNode[T]]:
        """Head işaretçisini saat yönünde (next) O(1) ilerletir."""
        if self._head is not None:
            self._head = self._head.next
        return self._head

    def rotate_backward(self) -> Optional[DoublyNode[T]]:
        """Head işaretçisini saat yönünün tersine (prev) O(1) geri alır."""
        if self._head is not None:
            self._head = self._head.prev
        return self._head

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[T]:
        """Yerleşik list kullanmadan generator (yield) ile ileri yönlü O(1) bellekli gezinme."""
        if self._head is None:
            return
        curr = self._head
        for _ in range(self._size):
            assert curr is not None
            yield curr.data
            curr = curr.next

    def iter_backward(self) -> Iterator[T]:
        """Tail düğümünden başlayarak geriye (prev) doğru generator ile gezinme."""
        tail = self.get_tail()
        if tail is None:
            return
        curr = tail
        for _ in range(self._size):
            assert curr is not None
            yield curr.data
            curr = curr.prev

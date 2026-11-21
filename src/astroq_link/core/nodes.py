"""Pointer-based DoublyNode and StackNode implementations."""

from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class DoublyNode(Generic[T]):
    """
    Çift yönlü dairesel bağlı liste düğümü.
    __slots__ kullanımı ile her düğümün RAM ayak izi minimumda tutulur.
    """
    __slots__ = ("data", "prev", "next")

    def __init__(self, data: T) -> None:
        self.data: T = data
        self.prev: Optional["DoublyNode[T]"] = None
        self.next: Optional["DoublyNode[T]"] = None


class StackNode(Generic[T]):
    """LIFO yığını için tek yönlü işaretçi düğümü."""
    __slots__ = ("data", "next")

    def __init__(self, data: T) -> None:
        self.data: T = data
        self.next: Optional["StackNode[T]"] = None

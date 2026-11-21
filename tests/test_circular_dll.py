
import pytest

from astroq_link.core import CircularDoublyLinkedList, RingBufferOverflowError


def test_empty_list_state() -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList(max_capacity=4)
    assert ring.is_empty() is True
    assert ring.size == 0
    assert len(ring) == 0
    assert ring.get_head() is None
    assert ring.get_tail() is None
    assert list(ring) == []


def test_single_node_circular_pointers() -> None:
    ring: CircularDoublyLinkedList[str] = CircularDoublyLinkedList()
    node = ring.append("CH-01")

    assert ring.size == 1
    assert ring.get_head() is node
    assert ring.get_tail() is node
    assert node.next is node
    assert node.prev is node


def test_forward_and_backward_traversal() -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList()
    for val in (10, 20, 30, 40):
        ring.append(val)

    assert list(ring) == [10, 20, 30, 40]
    assert list(ring.iter_backward()) == [40, 30, 20, 10]


def test_ring_buffer_overwrites_oldest_when_full() -> None:
    ring: CircularDoublyLinkedList[str] = CircularDoublyLinkedList(max_capacity=3, overwrite_on_full=True)
    ring.append("PKT-1")
    ring.append("PKT-2")
    ring.append("PKT-3")
    assert ring.is_full() is True

    # 4. paket geldiğinde kapasite 3'te sabit kalmalı ve en eski PKT-1 ezilmeli
    ring.append("PKT-4")
    assert ring.size == 3
    assert list(ring) == ["PKT-2", "PKT-3", "PKT-4"]
    assert ring.get_head().data == "PKT-2"  # type: ignore[union-attr]
    assert ring.get_tail().data == "PKT-4"  # type: ignore[union-attr]


def test_strict_capacity_raises_overflow() -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList(max_capacity=2, overwrite_on_full=False)
    ring.append(1)
    ring.append(2)

    with pytest.raises(RingBufferOverflowError):
        ring.append(3)


def test_remove_head_middle_tail_and_pointer_cleanup() -> None:
    ring: CircularDoublyLinkedList[str] = CircularDoublyLinkedList()
    n1 = ring.append("A")
    n2 = ring.append("B")
    n3 = ring.append("C")

    # Ortadaki düğümü sil
    removed = ring.remove_node(n2)
    assert removed == "B"
    assert n2.prev is None and n2.next is None  # Dangling reference temizliği
    assert list(ring) == ["A", "C"]

    # Head düğümünü sil
    ring.remove_node(n1)
    assert list(ring) == ["C"]
    assert ring.get_head() is n3
    assert n3.next is n3 and n3.prev is n3

    # Son kalan düğümü sil
    ring.remove_node(n3)
    assert ring.is_empty() is True
    assert ring.get_head() is None


def test_rotate_forward_and_backward() -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList()
    for i in (1, 2, 3):
        ring.append(i)

    ring.rotate_forward()
    assert list(ring) == [2, 3, 1]

    ring.rotate_backward()
    assert list(ring) == [1, 2, 3]

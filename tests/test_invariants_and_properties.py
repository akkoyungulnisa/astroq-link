"""Milestone 1 (P0): Structural invariants, edge cases, and property-based tests."""

from collections import deque
from typing import Any

from hypothesis import given, settings, strategies as st
import pytest

from astroq_link.core import CircularDoublyLinkedList, CriticalLIFOStack


def assert_ring_invariants(ring: CircularDoublyLinkedList[Any]) -> None:
    """Verify all structural and pointer invariants of CircularDoublyLinkedList."""
    items = list(ring)
    assert len(items) == ring.size

    if ring.max_capacity is not None:
        assert ring.size <= ring.max_capacity

    if ring.size == 0:
        assert ring.head is None
        assert ring.tail is None
        assert list(ring.iter_backward()) == []
        return

    assert ring.head is not None
    assert ring.tail is not None

    if ring.size == 1:
        assert ring.head is ring.tail
        assert ring.head.next is ring.head
        assert ring.head.prev is ring.head
        assert list(ring.iter_backward()) == items
        return

    # Multi-node circular pointer invariants
    assert ring.head.prev is ring.tail
    assert ring.tail.next is ring.head

    visited_ids: set[int] = set()
    forward_values: list[Any] = []
    curr = ring.head
    for _ in range(ring.size):
        assert curr is not None
        assert id(curr) not in visited_ids, "Duplicate node reference detected in ring!"
        visited_ids.add(id(curr))

        assert curr.next is not None and curr.next.prev is curr
        assert curr.prev is not None and curr.prev.next is curr

        forward_values.append(curr.data)
        curr = curr.next

    assert curr is ring.head
    assert forward_values == items
    assert list(ring.iter_backward()) == list(reversed(forward_values))


# ---------------------------------------------------------------------------
# 1.1 Circular Doubly Linked List Edge Cases & Invariants
# ---------------------------------------------------------------------------


def test_ring_capacity_one_lifecycle() -> None:
    ring: CircularDoublyLinkedList[str] = CircularDoublyLinkedList(
        max_capacity=1, overwrite_on_full=True
    )
    assert_ring_invariants(ring)

    node = ring.append("PKT-1")
    assert ring.size == 1
    assert list(ring) == ["PKT-1"]
    assert_ring_invariants(ring)

    # Single-element forward and backward rotation
    ring.rotate_forward()
    assert list(ring) == ["PKT-1"]
    assert_ring_invariants(ring)

    ring.rotate_backward()
    assert list(ring) == ["PKT-1"]
    assert_ring_invariants(ring)

    # Overwrite when capacity == 1
    ring.append("PKT-2")
    assert ring.size == 1
    assert list(ring) == ["PKT-2"]
    assert_ring_invariants(ring)

    # Remove single element and verify detached node cannot be removed twice
    assert ring.remove("PKT-2") is True
    assert ring.size == 0
    assert_ring_invariants(ring)

    with pytest.raises(ValueError):
        ring.remove_node(node)


def test_ring_empty_rotation_and_clear() -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList(max_capacity=4)
    ring.rotate_forward()
    ring.rotate_backward()
    assert_ring_invariants(ring)

    nodes = [ring.append(i) for i in range(4)]
    assert_ring_invariants(ring)

    ring.clear()
    assert ring.size == 0
    assert list(ring) == []
    assert_ring_invariants(ring)
    assert all(n.prev is None and n.next is None for n in nodes)


def test_ring_overwrite_and_removal_pointer_integrity() -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList(
        max_capacity=3, overwrite_on_full=True
    )
    for val in (10, 20, 30, 40, 50):
        ring.append(val)
        assert_ring_invariants(ring)

    assert list(ring) == [30, 40, 50]

    # Remove middle, head, and tail sequentially
    assert ring.remove(40) is True
    assert list(ring) == [30, 50]
    assert_ring_invariants(ring)

    assert ring.remove(30) is True
    assert list(ring) == [50]
    assert_ring_invariants(ring)

    assert ring.remove(50) is True
    assert list(ring) == []
    assert_ring_invariants(ring)


# ---------------------------------------------------------------------------
# 1.2 Critical LIFO Stack Edge Cases
# ---------------------------------------------------------------------------


def test_lifo_stack_capacity_one_and_empty_pop() -> None:
    stack: CriticalLIFOStack[str] = CriticalLIFOStack(max_capacity=1)
    assert stack.size == 0

    with pytest.raises((IndexError, Exception)):
        stack.pop()

    stack.push("CRITICAL-1")
    assert stack.size == 1
    assert stack.peek() == "CRITICAL-1"
    assert stack.pop() == "CRITICAL-1"
    assert stack.size == 0


def test_lifo_stack_blackout_ordering_and_clear() -> None:
    stack: CriticalLIFOStack[int] = CriticalLIFOStack(max_capacity=5)
    for seq in (101, 102, 103):
        stack.push(seq)

    # Latest telemetry packet must be recovered first
    assert stack.pop() == 103
    assert stack.pop() == 102
    stack.clear()
    assert stack.size == 0


# ---------------------------------------------------------------------------
# 1.3 Property-Based Testing (Hypothesis vs. collections.deque reference)
# ---------------------------------------------------------------------------


@settings(max_examples=300)
@given(
    capacity=st.integers(min_value=1, max_value=12),
    operations=st.lists(
        st.tuples(
            st.sampled_from(["append", "remove", "rot_fwd", "rot_bwd", "clear"]),
            st.integers(min_value=0, max_value=20),
        ),
        min_size=1,
        max_size=80,
    ),
)
def test_ring_matches_deque_reference_model(
    capacity: int, operations: list[tuple[str, int]]
) -> None:
    ring: CircularDoublyLinkedList[int] = CircularDoublyLinkedList(
        max_capacity=capacity, overwrite_on_full=True
    )
    ref: deque[int] = deque(maxlen=capacity)

    for op, value in operations:
        if op == "append":
            ring.append(value)
            ref.append(value)
        elif op == "remove":
            expected_removed = value in ref
            if expected_removed:
                ref.remove(value)
            actual_removed = ring.remove(value)
            assert actual_removed is expected_removed
        elif op == "rot_fwd":
            ring.rotate_forward()
            if ref:
                ref.rotate(-1)
        elif op == "rot_bwd":
            ring.rotate_backward()
            if ref:
                ref.rotate(1)
        elif op == "clear":
            ring.clear()
            ref.clear()

        assert_ring_invariants(ring)
        assert list(ring) == list(ref)
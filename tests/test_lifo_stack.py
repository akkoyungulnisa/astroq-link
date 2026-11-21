"""Edge-case unit tests for CriticalLIFOStack (overflow/underflow/rollback)."""

import pytest

from astroq_link.core import CriticalLIFOStack, StackOverflowError, StackUnderflowError


def test_empty_stack_underflow_and_safe_pop() -> None:
    stack: CriticalLIFOStack[str] = CriticalLIFOStack(max_capacity=3)
    assert stack.is_empty() is True
    assert stack.peek() is None
    assert stack.pop_safe() is None

    with pytest.raises(StackUnderflowError):
        stack.pop()


def test_lifo_order_and_peek() -> None:
    stack: CriticalLIFOStack[str] = CriticalLIFOStack()
    stack.push("ALT_1900m")
    stack.push("ALT_1925m")
    stack.push("ALT_1950m_BREACH")

    assert stack.size == 3
    assert stack.peek() == "ALT_1950m_BREACH"
    assert list(stack) == ["ALT_1950m_BREACH", "ALT_1925m", "ALT_1900m"]

    # Bağlantı açıldığında en güncel durum ilk sırada çıkmalı
    assert stack.pop() == "ALT_1950m_BREACH"
    assert stack.pop() == "ALT_1925m"
    assert stack.pop() == "ALT_1900m"
    assert stack.is_empty() is True


def test_stack_overflow_protection() -> None:
    stack: CriticalLIFOStack[int] = CriticalLIFOStack(max_capacity=2)
    stack.push(100)
    stack.push(200)
    assert stack.is_full() is True

    with pytest.raises(StackOverflowError):
        stack.push(300)


def test_stack_clear() -> None:
    stack: CriticalLIFOStack[int] = CriticalLIFOStack()
    for i in range(5):
        stack.push(i)

    stack.clear()
    assert stack.size == 0
    assert stack.is_empty() is True
    assert stack.peek() is None

"""
Pila (Stack) - LIFO: el ultimo que entra es el primero que sale.

En AlertaBarrio cada reporte tiene una pila con su historial de estados:

    created -> in_review -> published -> verified
                                           ^ tope

Cuando un moderador se equivoca y presiona "deshacer", hacemos pop() del
tope y el reporte vuelve al estado anterior (el nuevo tope). Es exactamente
el mismo mecanismo del Ctrl+Z de un editor de texto.

Implementada sobre nuestro DynamicArray. push/pop/peek son O(1).
"""

from typing import Any, Callable, Generic, Iterator, List, TypeVar

from .dynamic_array import DynamicArray

T = TypeVar("T")


class Stack(Generic[T]):
    def __init__(self) -> None:
        self._items: DynamicArray[T] = DynamicArray()

    def push(self, value: T) -> None:
        self._items.append(value)

    def pop(self) -> T:
        if self.is_empty():
            raise IndexError("pop sobre una pila vacia")
        return self._items.pop()

    def peek(self) -> T:
        if self.is_empty():
            raise IndexError("peek sobre una pila vacia")
        return self._items.get(len(self._items) - 1)

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        """Recorre desde el tope hasta la base."""
        for i in range(len(self._items) - 1, -1, -1):
            yield self._items.get(i)

    def to_list(self) -> List[T]:
        """Lista de tope -> base."""
        return list(iter(self))

    def __repr__(self) -> str:
        return f"Stack(top -> {self.to_list()})"

    def snapshot(self, mapper: Callable[[T], Any] = lambda x: x) -> dict:
        return {"type": "Stack", "size": len(self), "top_to_bottom": [mapper(v) for v in self]}

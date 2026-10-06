"""
Cola (Queue) - FIFO: el primero que entra es el primero que sale.

Implementada como un BUFFER CIRCULAR sobre un arreglo de tamano fijo que
crece cuando se llena. Asi enqueue y dequeue son O(1) sin tener que correr
elementos (como pasaria con list.pop(0), que es O(n)).

Uso en AlertaBarrio: cola de NOTIFICACIONES. Cuando se publica una alerta
en un barrio, se encola una notificacion por cada vecino suscrito, y un
proceso en segundo plano las va despachando en orden de llegada.
"""

from typing import Any, Callable, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")


class Queue(Generic[T]):
    def __init__(self, capacity: int = 8) -> None:
        self._data: List[Optional[T]] = [None] * max(1, capacity)
        self._front = 0  # indice del primer elemento
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    def _grow(self) -> None:
        old = self._data
        self._data = [None] * (len(old) * 2)
        # Copiamos "desenrollando" el circulo para que front quede en 0
        for i in range(self._size):
            self._data[i] = old[(self._front + i) % len(old)]
        self._front = 0

    def enqueue(self, value: T) -> None:
        if self._size == len(self._data):
            self._grow()
        rear = (self._front + self._size) % len(self._data)
        self._data[rear] = value
        self._size += 1

    def dequeue(self) -> T:
        if self.is_empty():
            raise IndexError("dequeue sobre una cola vacia")
        value = self._data[self._front]
        self._data[self._front] = None
        self._front = (self._front + 1) % len(self._data)
        self._size -= 1
        return value  # type: ignore[return-value]

    def peek(self) -> T:
        if self.is_empty():
            raise IndexError("peek sobre una cola vacia")
        return self._data[self._front]  # type: ignore[return-value]

    def __iter__(self) -> Iterator[T]:
        for i in range(self._size):
            yield self._data[(self._front + i) % len(self._data)]  # type: ignore[misc]

    def to_list(self) -> List[T]:
        return list(iter(self))

    def __repr__(self) -> str:
        return f"Queue(front -> {self.to_list()})"

    def snapshot(self, mapper: Callable[[T], Any] = lambda x: x) -> dict:
        return {
            "type": "Queue (buffer circular)",
            "size": self._size,
            "capacity": len(self._data),
            "front_index": self._front,
            "front_to_rear": [mapper(v) for v in self],
        }

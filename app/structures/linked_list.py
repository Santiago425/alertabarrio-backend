"""
Lista doblemente enlazada (Doubly Linked List).

La usamos para el FEED de alertas activas de cada barrio: cada vez que se
publica un reporte se inserta al INICIO (lo mas reciente arriba), y cuando
un moderador deshace una publicacion se elimina el nodo. Insertar al inicio
y borrar un nodo conocido es O(1), que es justo lo que necesita un feed.

Complejidades:
    - push_front / push_back ...... O(1)
    - pop_front / pop_back ........ O(1)
    - remove(valor) ............... O(n) (hay que buscar el nodo)
    - recorrer .................... O(n)
"""

from typing import Any, Callable, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")


class Node(Generic[T]):
    __slots__ = ("value", "prev", "next")

    def __init__(self, value: T) -> None:
        self.value = value
        self.prev: Optional["Node[T]"] = None
        self.next: Optional["Node[T]"] = None


class LinkedList(Generic[T]):
    def __init__(self) -> None:
        self.head: Optional[Node[T]] = None
        self.tail: Optional[Node[T]] = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    def push_front(self, value: T) -> Node[T]:
        node = Node(value)
        node.next = self.head
        if self.head is not None:
            self.head.prev = node
        self.head = node
        if self.tail is None:
            self.tail = node
        self._size += 1
        return node

    def push_back(self, value: T) -> Node[T]:
        node = Node(value)
        node.prev = self.tail
        if self.tail is not None:
            self.tail.next = node
        self.tail = node
        if self.head is None:
            self.head = node
        self._size += 1
        return node

    def _unlink(self, node: Node[T]) -> T:
        if node.prev is not None:
            node.prev.next = node.next
        else:
            self.head = node.next
        if node.next is not None:
            node.next.prev = node.prev
        else:
            self.tail = node.prev
        node.prev = node.next = None
        self._size -= 1
        return node.value

    def pop_front(self) -> T:
        if self.head is None:
            raise IndexError("pop_front sobre lista vacia")
        return self._unlink(self.head)

    def pop_back(self) -> T:
        if self.tail is None:
            raise IndexError("pop_back sobre lista vacia")
        return self._unlink(self.tail)

    def find(self, predicate: Callable[[T], bool]) -> Optional[Node[T]]:
        current = self.head
        while current is not None:
            if predicate(current.value):
                return current
            current = current.next
        return None

    def remove_first(self, predicate: Callable[[T], bool]) -> Optional[T]:
        node = self.find(predicate)
        if node is None:
            return None
        return self._unlink(node)

    def insert_sorted(self, value: T, key: Callable[[T], Any], descending: bool = True) -> None:
        """Inserta manteniendo el orden (sirve para el historial por fecha)."""
        current = self.head
        while current is not None:
            a, b = key(value), key(current.value)
            if (a >= b) if descending else (a <= b):
                break
            current = current.next
        if current is None:
            self.push_back(value)
            return
        if current is self.head:
            self.push_front(value)
            return
        node = Node(value)
        prev = current.prev
        node.prev, node.next = prev, current
        prev.next = node  # type: ignore[union-attr]
        current.prev = node
        self._size += 1

    def __iter__(self) -> Iterator[T]:
        current = self.head
        while current is not None:
            yield current.value
            current = current.next

    def reverse_iter(self) -> Iterator[T]:
        current = self.tail
        while current is not None:
            yield current.value
            current = current.prev

    def to_list(self, limit: Optional[int] = None) -> List[T]:
        result: List[T] = []
        for value in self:
            if limit is not None and len(result) >= limit:
                break
            result.append(value)
        return result

    def __repr__(self) -> str:
        return " <-> ".join(str(v) for v in self) or "LinkedList(vacia)"

    def snapshot(self, mapper: Callable[[T], Any] = lambda x: x) -> dict:
        return {"type": "LinkedList", "size": self._size, "items": [mapper(v) for v in self]}

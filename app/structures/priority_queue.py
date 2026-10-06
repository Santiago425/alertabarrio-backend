"""
Cola de prioridad (Priority Queue) implementada con un MAX-HEAP binario.

Es el corazon de AlertaBarrio: los reportes nuevos entran a la cola de
moderacion y SIEMPRE sale primero el mas grave (un robo armado antes que
un hurto o una actividad sospechosa), aunque haya llegado despues.
Si dos reportes tienen la misma prioridad, sale el que llego primero.

El heap se guarda en nuestro DynamicArray:
    padre(i) = (i - 1) // 2
    hijo_izq(i) = 2i + 1
    hijo_der(i) = 2i + 2

Ademas guardamos en una HashTable la posicion de cada elemento dentro del
heap, asi podemos sacar un reporte especifico (cuando el moderador lo abre
directamente) en O(log n) en vez de O(n).

Complejidades:
    push ............ O(log n)   (sift-up)
    pop (el mayor) .. O(log n)   (sift-down)
    peek ............ O(1)
    remove(id) ...... O(log n)   gracias a la tabla de posiciones
"""

from typing import Any, Callable, Generic, Hashable, List, Optional, Tuple, TypeVar

from .dynamic_array import DynamicArray
from .hash_table import HashTable

T = TypeVar("T")

# Una entrada del heap: (prioridad, contador_de_llegada, id, valor)
# El contador desempata: a igual prioridad sale el que llego primero (FIFO).


class PriorityQueue(Generic[T]):
    def __init__(self, priority_of: Callable[[T], float], id_of: Callable[[T], Hashable]) -> None:
        self._heap: DynamicArray[Tuple[float, int, Hashable, T]] = DynamicArray()
        self._positions: HashTable[Hashable, int] = HashTable()
        self._priority_of = priority_of
        self._id_of = id_of
        self._counter = 0

    # --------------------------------------------------------- comparacion
    @staticmethod
    def _higher(a: Tuple[float, int, Any, Any], b: Tuple[float, int, Any, Any]) -> bool:
        """True si `a` debe salir antes que `b`."""
        if a[0] != b[0]:
            return a[0] > b[0]  # mayor prioridad primero
        return a[1] < b[1]  # empate: el que llego primero

    def _swap(self, i: int, j: int) -> None:
        self._heap.swap(i, j)
        self._positions.put(self._heap[i][2], i)
        self._positions.put(self._heap[j][2], j)

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._higher(self._heap[i], self._heap[parent]):
                self._swap(i, parent)
                i = parent
            else:
                break

    def _sift_down(self, i: int) -> None:
        n = len(self._heap)
        while True:
            best = i
            left, right = 2 * i + 1, 2 * i + 2
            if left < n and self._higher(self._heap[left], self._heap[best]):
                best = left
            if right < n and self._higher(self._heap[right], self._heap[best]):
                best = right
            if best == i:
                return
            self._swap(i, best)
            i = best

    # ------------------------------------------------------------ publico
    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def __contains__(self, item_id: Hashable) -> bool:
        return item_id in self._positions

    def push(self, value: T) -> None:
        item_id = self._id_of(value)
        if item_id in self._positions:
            # Si ya estaba, lo actualizamos (por ejemplo si la IA cambio su prioridad)
            self.remove(item_id)
        entry = (float(self._priority_of(value)), self._counter, item_id, value)
        self._counter += 1
        self._heap.append(entry)
        self._positions.put(item_id, len(self._heap) - 1)
        self._sift_up(len(self._heap) - 1)

    def peek(self) -> T:
        if self.is_empty():
            raise IndexError("peek sobre cola de prioridad vacia")
        return self._heap[0][3]

    def pop(self) -> T:
        if self.is_empty():
            raise IndexError("pop sobre cola de prioridad vacia")
        last = len(self._heap) - 1
        self._swap(0, last)
        entry = self._heap.pop()
        self._positions.remove(entry[2])
        if not self.is_empty():
            self._sift_down(0)
        return entry[3]

    def remove(self, item_id: Hashable) -> Optional[T]:
        index = self._positions.get(item_id)
        if index is None:
            return None
        last = len(self._heap) - 1
        if index != last:
            self._swap(index, last)
        entry = self._heap.pop()
        self._positions.remove(item_id)
        if index < len(self._heap):
            # El elemento que movimos a ese hueco puede tener que subir o bajar
            moved_id = self._heap[index][2]
            self._sift_up(index)
            self._sift_down(self._positions.get(moved_id))
        return entry[3]

    def ordered(self) -> List[T]:
        """Devuelve los elementos en el orden en que saldrian, SIN modificar
        el heap original (hacemos heapsort sobre una copia)."""
        copy: PriorityQueue[T] = PriorityQueue(self._priority_of, self._id_of)
        for entry in self._heap:
            copy._heap.append(entry)
            copy._positions.put(entry[2], len(copy._heap) - 1)
        copy._counter = self._counter
        result: List[T] = []
        while not copy.is_empty():
            result.append(copy.pop())
        return result

    def heap_array(self) -> List[Tuple[float, Hashable]]:
        """El arreglo interno tal cual (para dibujar el arbol en el frontend)."""
        return [(e[0], e[2]) for e in self._heap]

    def snapshot(self, mapper: Callable[[T], Any] = lambda x: x) -> dict:
        return {
            "type": "PriorityQueue (max-heap)",
            "size": len(self),
            "heap_array": [{"priority": p, "id": i} for p, i in self.heap_array()],
            "pop_order": [mapper(v) for v in self.ordered()],
        }

"""
Arreglo dinamico (Dynamic Array).

Python ya trae `list`, pero en la materia vimos como funciona por dentro:
un arreglo de tamano fijo que se duplica cuando se llena. Aqui lo
implementamos "a mano" usando un arreglo de capacidad fija y lo usamos
como base para la Pila (Stack) y para el Heap de la cola de prioridad.

Complejidades:
    - get / set por indice ........ O(1)
    - append ...................... O(1) amortizado (se duplica la capacidad)
    - pop al final ................ O(1) amortizado
    - insert / remove en medio .... O(n) (hay que correr los elementos)
"""

from typing import Any, Callable, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")


class DynamicArray(Generic[T]):
    INITIAL_CAPACITY = 4

    def __init__(self, capacity: int = INITIAL_CAPACITY) -> None:
        self._capacity = max(1, capacity)
        self._size = 0
        # Simulamos un bloque de memoria de tamano fijo
        self._data: List[Optional[T]] = [None] * self._capacity

    # ------------------------------------------------------------------ util
    def _check_index(self, index: int) -> None:
        if index < 0 or index >= self._size:
            raise IndexError(f"Indice {index} fuera de rango (tamano {self._size})")

    def _resize(self, new_capacity: int) -> None:
        """Crea un bloque nuevo y copia los elementos: O(n)."""
        new_data: List[Optional[T]] = [None] * new_capacity
        for i in range(self._size):
            new_data[i] = self._data[i]
        self._data = new_data
        self._capacity = new_capacity

    # --------------------------------------------------------------- basicos
    def __len__(self) -> int:
        return self._size

    @property
    def capacity(self) -> int:
        return self._capacity

    def is_empty(self) -> bool:
        return self._size == 0

    def get(self, index: int) -> T:
        self._check_index(index)
        return self._data[index]  # type: ignore[return-value]

    def set(self, index: int, value: T) -> None:
        self._check_index(index)
        self._data[index] = value

    __getitem__ = get
    __setitem__ = set

    def append(self, value: T) -> None:
        if self._size == self._capacity:
            self._resize(self._capacity * 2)
        self._data[self._size] = value
        self._size += 1

    def insert(self, index: int, value: T) -> None:
        if index < 0 or index > self._size:
            raise IndexError(f"Indice {index} fuera de rango")
        if self._size == self._capacity:
            self._resize(self._capacity * 2)
        # Corremos los elementos una posicion a la derecha
        for i in range(self._size, index, -1):
            self._data[i] = self._data[i - 1]
        self._data[index] = value
        self._size += 1

    def pop(self) -> T:
        if self._size == 0:
            raise IndexError("pop sobre un arreglo vacio")
        self._size -= 1
        value = self._data[self._size]
        self._data[self._size] = None
        # Si queda muy vacio, reducimos a la mitad para no desperdiciar memoria
        if 0 < self._size <= self._capacity // 4 and self._capacity > self.INITIAL_CAPACITY:
            self._resize(self._capacity // 2)
        return value  # type: ignore[return-value]

    def remove_at(self, index: int) -> T:
        self._check_index(index)
        value = self._data[index]
        for i in range(index, self._size - 1):
            self._data[i] = self._data[i + 1]
        self._size -= 1
        self._data[self._size] = None
        return value  # type: ignore[return-value]

    def index_of(self, predicate: Callable[[T], bool]) -> int:
        """Busqueda lineal O(n). Devuelve -1 si no lo encuentra."""
        for i in range(self._size):
            if predicate(self._data[i]):  # type: ignore[arg-type]
                return i
        return -1

    def swap(self, i: int, j: int) -> None:
        self._check_index(i)
        self._check_index(j)
        self._data[i], self._data[j] = self._data[j], self._data[i]

    def clear(self) -> None:
        self._capacity = self.INITIAL_CAPACITY
        self._size = 0
        self._data = [None] * self._capacity

    def __iter__(self) -> Iterator[T]:
        for i in range(self._size):
            yield self._data[i]  # type: ignore[misc]

    def to_list(self) -> List[T]:
        return [self._data[i] for i in range(self._size)]  # type: ignore[misc]

    def __repr__(self) -> str:
        return f"DynamicArray(size={self._size}, capacity={self._capacity}, data={self.to_list()})"

    def snapshot(self, mapper: Callable[[T], Any] = lambda x: x) -> dict:
        return {
            "type": "DynamicArray",
            "size": self._size,
            "capacity": self._capacity,
            "items": [mapper(x) for x in self],
        }

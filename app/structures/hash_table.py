"""
Tabla Hash (Hash Table) con encadenamiento separado (separate chaining).

Cada "bucket" es una lista de pares (clave, valor). Cuando dos claves caen
en el mismo bucket (colision) simplemente se agregan a esa lista.
Si el factor de carga (elementos / buckets) supera 0.75 duplicamos el
numero de buckets y volvemos a distribuir (rehash).

Uso en AlertaBarrio:
    - barrio_id  -> lista de vecinos suscritos (para notificar)
    - barrio_id  -> feed (LinkedList) de alertas del barrio
    - reporte_id -> pila (Stack) con el historial de estados
    - reporte_id -> posicion dentro del heap (para sacar un reporte en O(log n))

Complejidades promedio: put / get / remove O(1). Peor caso O(n).
"""

from typing import Any, Callable, Generic, Iterator, List, Optional, Tuple, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class HashTable(Generic[K, V]):
    MAX_LOAD_FACTOR = 0.75

    def __init__(self, buckets: int = 16) -> None:
        self._buckets: List[List[Tuple[K, V]]] = [[] for _ in range(max(1, buckets))]
        self._size = 0
        self.collisions = 0  # contador para mostrarlo en la presentacion

    def _index(self, key: K) -> int:
        # hash() de Python + modulo. Para enteros hash(x) == x.
        return hash(key) % len(self._buckets)

    @property
    def load_factor(self) -> float:
        return self._size / len(self._buckets)

    def _rehash(self) -> None:
        old = self._buckets
        self._buckets = [[] for _ in range(len(old) * 2)]
        self._size = 0
        self.collisions = 0
        for bucket in old:
            for k, v in bucket:
                self.put(k, v)

    def put(self, key: K, value: V) -> None:
        bucket = self._buckets[self._index(key)]
        for i, (k, _) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)  # actualizar
                return
        if bucket:
            self.collisions += 1
        bucket.append((key, value))
        self._size += 1
        if self.load_factor > self.MAX_LOAD_FACTOR:
            self._rehash()

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        for k, v in self._buckets[self._index(key)]:
            if k == key:
                return v
        return default

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        value = self.get(key)
        if value is None:
            value = factory()
            self.put(key, value)
        return value

    def contains(self, key: K) -> bool:
        return any(k == key for k, _ in self._buckets[self._index(key)])

    __contains__ = contains

    def remove(self, key: K) -> Optional[V]:
        bucket = self._buckets[self._index(key)]
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket.pop(i)
                self._size -= 1
                return v
        return None

    def __len__(self) -> int:
        return self._size

    def keys(self) -> Iterator[K]:
        for bucket in self._buckets:
            for k, _ in bucket:
                yield k

    def items(self) -> Iterator[Tuple[K, V]]:
        for bucket in self._buckets:
            for pair in bucket:
                yield pair

    def snapshot(self, mapper: Callable[[V], Any] = lambda x: x) -> dict:
        return {
            "type": "HashTable (encadenamiento)",
            "size": self._size,
            "buckets": len(self._buckets),
            "load_factor": round(self.load_factor, 3),
            "collisions": self.collisions,
            "bucket_lengths": [len(b) for b in self._buckets],
            "entries": {str(k): mapper(v) for k, v in self.items()},
        }

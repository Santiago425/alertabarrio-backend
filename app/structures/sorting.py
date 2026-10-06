"""
Algoritmos de ordenamiento y busqueda vistos en clase.

    - merge_sort: estable, O(n log n). Lo usamos para ordenar el feed
      general (varios barrios) por prioridad y fecha. Al ser ESTABLE, si dos
      alertas tienen la misma prioridad conservan su orden por fecha.
    - quick_sort: O(n log n) promedio. Lo usamos para el ranking de barrios
      mas peligrosos (no necesitamos estabilidad).
    - binary_search: O(log n) sobre una lista ordenada. Lo usamos para
      buscar un barrio por nombre en el catalogo ordenado.
"""

from typing import Any, Callable, List, Optional, TypeVar

T = TypeVar("T")


def merge_sort(items: List[T], key: Callable[[T], Any] = lambda x: x, reverse: bool = False) -> List[T]:
    if len(items) <= 1:
        return list(items)
    mid = len(items) // 2
    left = merge_sort(items[:mid], key, reverse)
    right = merge_sort(items[mid:], key, reverse)
    return _merge(left, right, key, reverse)


def _merge(left: List[T], right: List[T], key: Callable[[T], Any], reverse: bool) -> List[T]:
    result: List[T] = []
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = key(left[i]), key(right[j])
        # Con <= (o >=) tomamos primero el de la izquierda en empate -> estable
        take_left = a >= b if reverse else a <= b
        if take_left:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


def quick_sort(items: List[T], key: Callable[[T], Any] = lambda x: x, reverse: bool = False) -> List[T]:
    if len(items) <= 1:
        return list(items)
    pivot = key(items[len(items) // 2])  # pivote = elemento del medio
    less = [x for x in items if key(x) < pivot]
    equal = [x for x in items if key(x) == pivot]
    greater = [x for x in items if key(x) > pivot]
    if reverse:
        return quick_sort(greater, key, True) + equal + quick_sort(less, key, True)
    return quick_sort(less, key) + equal + quick_sort(greater, key)


def binary_search(sorted_items: List[T], target: Any, key: Callable[[T], Any] = lambda x: x) -> Optional[int]:
    low, high = 0, len(sorted_items) - 1
    while low <= high:
        mid = (low + high) // 2
        value = key(sorted_items[mid])
        if value == target:
            return mid
        if value < target:
            low = mid + 1
        else:
            high = mid - 1
    return None

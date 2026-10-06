"""
Arbol Binario de Busqueda (BST) balanceado tipo AVL.

Guardamos el historial completo de reportes indexado por FECHA (timestamp).
Con el arbol podemos responder rapido preguntas como "dame todos los
reportes entre el 1 y el 15 de septiembre" sin recorrer toda la tabla:
solo bajamos por las ramas que pueden tener fechas dentro del rango.

Como los reportes llegan casi siempre en orden de fecha, un BST normal se
volveria una "lista" (altura n). Por eso lo balanceamos con rotaciones AVL
y la altura queda en O(log n).

Varios reportes pueden tener la misma fecha, por eso cada nodo guarda una
lista de valores.

Complejidades: insert O(log n), search O(log n), range O(log n + k).
"""

from typing import Any, Callable, Generic, List, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BSTNode(Generic[K, V]):
    __slots__ = ("key", "values", "left", "right", "height")

    def __init__(self, key: K, value: V) -> None:
        self.key = key
        self.values: List[V] = [value]
        self.left: Optional["BSTNode[K, V]"] = None
        self.right: Optional["BSTNode[K, V]"] = None
        self.height = 1


def _h(node: Optional[BSTNode]) -> int:
    return node.height if node else 0


class BinarySearchTree(Generic[K, V]):
    def __init__(self) -> None:
        self.root: Optional[BSTNode[K, V]] = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    @property
    def height(self) -> int:
        return _h(self.root)

    # -------------------------------------------------------- rotaciones
    @staticmethod
    def _update(node: BSTNode) -> None:
        node.height = 1 + max(_h(node.left), _h(node.right))

    def _rotate_right(self, y: BSTNode) -> BSTNode:
        x = y.left
        y.left = x.right
        x.right = y
        self._update(y)
        self._update(x)
        return x

    def _rotate_left(self, x: BSTNode) -> BSTNode:
        y = x.right
        x.right = y.left
        y.left = x
        self._update(x)
        self._update(y)
        return y

    def _balance(self, node: BSTNode) -> BSTNode:
        self._update(node)
        factor = _h(node.left) - _h(node.right)
        if factor > 1:  # cargado a la izquierda
            if _h(node.left.left) < _h(node.left.right):
                node.left = self._rotate_left(node.left)
            return self._rotate_right(node)
        if factor < -1:  # cargado a la derecha
            if _h(node.right.right) < _h(node.right.left):
                node.right = self._rotate_right(node.right)
            return self._rotate_left(node)
        return node

    # ---------------------------------------------------------- insertar
    def insert(self, key: K, value: V) -> None:
        self.root = self._insert(self.root, key, value)
        self._size += 1

    def _insert(self, node: Optional[BSTNode], key: K, value: V) -> BSTNode:
        if node is None:
            return BSTNode(key, value)
        if key < node.key:
            node.left = self._insert(node.left, key, value)
        elif key > node.key:
            node.right = self._insert(node.right, key, value)
        else:
            node.values.append(value)
            return node
        return self._balance(node)

    # ----------------------------------------------------------- eliminar
    def remove_value(self, key: K, predicate: Callable[[V], bool]) -> bool:
        """Quita un valor especifico de la clave. Si el nodo queda vacio se
        elimina el nodo del arbol."""
        node = self.root
        while node is not None and node.key != key:
            node = node.left if key < node.key else node.right
        if node is None:
            return False
        for i, v in enumerate(node.values):
            if predicate(v):
                node.values.pop(i)
                self._size -= 1
                if not node.values:
                    self.root = self._delete(self.root, key)
                return True
        return False

    def _delete(self, node: Optional[BSTNode], key: K) -> Optional[BSTNode]:
        if node is None:
            return None
        if key < node.key:
            node.left = self._delete(node.left, key)
        elif key > node.key:
            node.right = self._delete(node.right, key)
        else:
            if node.left is None:
                return node.right
            if node.right is None:
                return node.left
            # Dos hijos: reemplazamos por el sucesor (el minimo de la derecha)
            successor = node.right
            while successor.left is not None:
                successor = successor.left
            node.key, node.values = successor.key, successor.values
            successor.values = []
            node.right = self._delete_min(node.right)
        return self._balance(node)

    def _delete_min(self, node: BSTNode) -> Optional[BSTNode]:
        if node.left is None:
            return node.right
        node.left = self._delete_min(node.left)
        return self._balance(node)

    # ----------------------------------------------------------- consultas
    def search(self, key: K) -> List[V]:
        node = self.root
        while node is not None:
            if key == node.key:
                return list(node.values)
            node = node.left if key < node.key else node.right
        return []

    def range_query(self, low: K, high: K) -> List[V]:
        """Todos los valores con low <= clave <= high, en orden ascendente."""
        result: List[V] = []
        self._range(self.root, low, high, result)
        return result

    def _range(self, node: Optional[BSTNode], low: K, high: K, out: List[V]) -> None:
        if node is None:
            return
        if low < node.key:  # puede haber claves validas a la izquierda
            self._range(node.left, low, high, out)
        if low <= node.key <= high:
            out.extend(node.values)
        if node.key < high:  # puede haber claves validas a la derecha
            self._range(node.right, low, high, out)

    def in_order(self) -> List[V]:
        result: List[V] = []

        def walk(node: Optional[BSTNode]) -> None:
            if node is None:
                return
            walk(node.left)
            result.extend(node.values)
            walk(node.right)

        walk(self.root)
        return result

    def min_key(self) -> Optional[K]:
        node = self.root
        if node is None:
            return None
        while node.left is not None:
            node = node.left
        return node.key

    def max_key(self) -> Optional[K]:
        node = self.root
        if node is None:
            return None
        while node.right is not None:
            node = node.right
        return node.key

    def snapshot(self, key_mapper: Callable[[K], Any] = lambda x: x, max_depth: int = 4) -> dict:
        def to_dict(node: Optional[BSTNode], depth: int) -> Optional[dict]:
            if node is None or depth > max_depth:
                return None
            return {
                "key": key_mapper(node.key),
                "count": len(node.values),
                "left": to_dict(node.left, depth + 1),
                "right": to_dict(node.right, depth + 1),
            }

        return {
            "type": "BinarySearchTree (AVL)",
            "size": self._size,
            "height": self.height,
            "min": key_mapper(self.min_key()) if self.root else None,
            "max": key_mapper(self.max_key()) if self.root else None,
            "tree": to_dict(self.root, 1),
        }

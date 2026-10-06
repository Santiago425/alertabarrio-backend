"""
Grafo ponderado NO dirigido con lista de adyacencia.

Cada BARRIO es un vertice y cada calle/avenida que conecta dos barrios es
una arista con peso = distancia en metros.

Usamos tres algoritmos vistos en clase:
    - BFS (recorrido en anchura, usa nuestra Queue): ruta con MENOS barrios.
    - DFS (recorrido en profundidad, usa nuestra Stack): saber si toda la
      ciudad esta conectada / que barrios son alcanzables.
    - DIJKSTRA (usa nuestra PriorityQueue): ruta MAS SEGURA. El peso de
      cada arista se "castiga" segun las alertas activas del barrio al que
      se llega, asi el camino evita las zonas con robos recientes aunque
      sea un poco mas largo.

Complejidades: BFS/DFS O(V + E), Dijkstra O((V + E) log V).
"""

from typing import Callable, Dict, Hashable, List, Optional, Tuple

from .dynamic_array import DynamicArray
from .hash_table import HashTable
from .priority_queue import PriorityQueue
from .queue import Queue
from .stack import Stack

INF = float("inf")


class Graph:
    def __init__(self) -> None:
        # vertice -> arreglo de (vecino, peso)
        self._adj: HashTable[Hashable, DynamicArray[Tuple[Hashable, float]]] = HashTable()
        self._labels: HashTable[Hashable, str] = HashTable()
        self._edges = 0

    def add_vertex(self, v: Hashable, label: str = "") -> None:
        if v not in self._adj:
            self._adj.put(v, DynamicArray())
        if label:
            self._labels.put(v, label)

    def add_edge(self, u: Hashable, v: Hashable, weight: float) -> None:
        self.add_vertex(u)
        self.add_vertex(v)
        self._adj.get(u).append((v, weight))
        self._adj.get(v).append((u, weight))
        self._edges += 1

    def neighbors(self, v: Hashable) -> List[Tuple[Hashable, float]]:
        arr = self._adj.get(v)
        return arr.to_list() if arr is not None else []

    def vertices(self) -> List[Hashable]:
        return list(self._adj.keys())

    def label(self, v: Hashable) -> str:
        return self._labels.get(v, str(v)) or str(v)

    @property
    def vertex_count(self) -> int:
        return len(self._adj)

    @property
    def edge_count(self) -> int:
        return self._edges

    # ---------------------------------------------------------------- BFS
    def bfs_path(self, start: Hashable, goal: Hashable) -> Optional[List[Hashable]]:
        """Camino con el menor numero de saltos (barrios)."""
        if start not in self._adj or goal not in self._adj:
            return None
        parent: Dict[Hashable, Optional[Hashable]] = {start: None}
        queue: Queue[Hashable] = Queue()
        queue.enqueue(start)
        while not queue.is_empty():
            current = queue.dequeue()
            if current == goal:
                break
            for neighbor, _ in self.neighbors(current):
                if neighbor not in parent:
                    parent[neighbor] = current
                    queue.enqueue(neighbor)
        if goal not in parent:
            return None
        return self._rebuild(parent, goal)

    # ---------------------------------------------------------------- DFS
    def dfs_reachable(self, start: Hashable) -> List[Hashable]:
        """Todos los barrios alcanzables desde `start` (DFS iterativo)."""
        if start not in self._adj:
            return []
        visited: Dict[Hashable, bool] = {}
        order: List[Hashable] = []
        stack: Stack[Hashable] = Stack()
        stack.push(start)
        while not stack.is_empty():
            current = stack.pop()
            if visited.get(current):
                continue
            visited[current] = True
            order.append(current)
            for neighbor, _ in self.neighbors(current):
                if not visited.get(neighbor):
                    stack.push(neighbor)
        return order

    def is_connected(self) -> bool:
        vs = self.vertices()
        return not vs or len(self.dfs_reachable(vs[0])) == len(vs)

    # ----------------------------------------------------------- Dijkstra
    def dijkstra(
        self,
        start: Hashable,
        goal: Hashable,
        penalty: Callable[[Hashable], float] = lambda v: 0.0,
    ) -> Tuple[Optional[List[Hashable]], float]:
        """Camino de costo minimo. El costo de entrar al vertice v es
        peso_arista * (1 + penalty(v)). Con penalty = 0 es la ruta mas corta."""
        if start not in self._adj or goal not in self._adj:
            return None, INF
        dist: Dict[Hashable, float] = {start: 0.0}
        parent: Dict[Hashable, Optional[Hashable]] = {start: None}
        done: Dict[Hashable, bool] = {}
        # Nuestra PQ es de maximos, por eso usamos prioridad = -distancia
        pq: PriorityQueue[Tuple[Hashable, float]] = PriorityQueue(
            priority_of=lambda item: -item[1], id_of=lambda item: item[0]
        )
        pq.push((start, 0.0))
        while not pq.is_empty():
            current, d = pq.pop()
            if done.get(current):
                continue
            done[current] = True
            if current == goal:
                break
            for neighbor, weight in self.neighbors(current):
                if done.get(neighbor):
                    continue
                cost = d + weight * (1.0 + penalty(neighbor))
                if cost < dist.get(neighbor, INF):
                    dist[neighbor] = cost
                    parent[neighbor] = current
                    pq.push((neighbor, cost))  # push actualiza si ya estaba (decrease-key)
        if goal not in dist:
            return None, INF
        return self._rebuild(parent, goal), dist[goal]

    def path_length(self, path: List[Hashable]) -> float:
        total = 0.0
        for a, b in zip(path, path[1:]):
            total += min((w for n, w in self.neighbors(a) if n == b), default=INF)
        return total

    @staticmethod
    def _rebuild(parent: Dict[Hashable, Optional[Hashable]], goal: Hashable) -> List[Hashable]:
        # Reconstruimos el camino con una pila para dejarlo en orden inicio -> fin
        stack: Stack[Hashable] = Stack()
        node: Optional[Hashable] = goal
        while node is not None:
            stack.push(node)
            node = parent[node]
        path: List[Hashable] = []
        while not stack.is_empty():
            path.append(stack.pop())
        return path

    def snapshot(self) -> dict:
        return {
            "type": "Graph (lista de adyacencia)",
            "vertices": self.vertex_count,
            "edges": self.edge_count,
            "connected": self.is_connected(),
            "adjacency": {
                self.label(v): [{"to": self.label(n), "meters": w} for n, w in self.neighbors(v)]
                for v in self.vertices()
            },
        }

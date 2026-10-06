"""Pruebas unitarias de nuestras estructuras de datos."""

import random

import pytest

from app.structures import (
    BinarySearchTree,
    DynamicArray,
    Graph,
    HashTable,
    LinkedList,
    PriorityQueue,
    Queue,
    Stack,
    binary_search,
    merge_sort,
    quick_sort,
)


def test_dynamic_array_grows_and_shrinks():
    arr = DynamicArray()
    for i in range(20):
        arr.append(i)
    assert len(arr) == 20 and arr.capacity >= 20
    arr.insert(0, -1)
    assert arr[0] == -1 and arr[1] == 0
    assert arr.remove_at(0) == -1
    while len(arr) > 2:
        arr.pop()
    assert arr.capacity < 32
    with pytest.raises(IndexError):
        arr.get(5)


def test_stack_lifo():
    s = Stack()
    for state in ["created", "in_review", "published"]:
        s.push(state)
    assert s.peek() == "published"
    assert s.pop() == "published"
    assert s.to_list() == ["in_review", "created"]
    s.pop(), s.pop()
    with pytest.raises(IndexError):
        s.pop()


def test_queue_fifo_circular_buffer():
    q = Queue(capacity=2)
    for i in range(5):
        q.enqueue(i)
    assert q.dequeue() == 0
    q.enqueue(5)
    assert q.to_list() == [1, 2, 3, 4, 5]
    assert [q.dequeue() for _ in range(5)] == [1, 2, 3, 4, 5]
    assert q.is_empty()


def test_linked_list_operations():
    ll = LinkedList()
    ll.push_back(2)
    ll.push_front(1)
    ll.push_back(3)
    assert ll.to_list() == [1, 2, 3]
    assert ll.remove_first(lambda x: x == 2) == 2
    assert list(ll.reverse_iter()) == [3, 1]
    ll.insert_sorted(2, key=lambda x: x, descending=False)
    assert ll.to_list() == [1, 2, 3]


def test_hash_table_rehash_and_collisions():
    h = HashTable(buckets=2)
    for i in range(100):
        h.put(i, i * i)
    assert len(h) == 100
    assert h.get(7) == 49
    h.put(7, 0)
    assert h.get(7) == 0 and len(h) == 100
    assert h.remove(7) == 0 and 7 not in h
    assert h.load_factor <= HashTable.MAX_LOAD_FACTOR


def test_priority_queue_order_and_tie_break():
    pq = PriorityQueue(priority_of=lambda r: r["p"], id_of=lambda r: r["id"])
    pq.push({"id": 1, "p": 2})  # sospecha
    pq.push({"id": 2, "p": 5})  # robo armado
    pq.push({"id": 3, "p": 3})  # hurto
    pq.push({"id": 4, "p": 5})  # otro robo armado, llego despues
    assert [r["id"] for r in pq.ordered()] == [2, 4, 3, 1]
    assert pq.remove(4)["id"] == 4
    assert [pq.pop()["id"] for _ in range(3)] == [2, 3, 1]


def test_priority_queue_random_matches_sorted():
    rng = random.Random(1)
    pq = PriorityQueue(priority_of=lambda x: x[1], id_of=lambda x: x[0])
    items = [(i, rng.randint(0, 50)) for i in range(200)]
    for it in items:
        pq.push(it)
    for i in range(0, 200, 7):
        pq.remove(i)
    expected = sorted([it for it in items if it[0] % 7 != 0], key=lambda x: (-x[1], x[0]))
    assert [pq.pop() for _ in range(len(pq))] == expected


def test_bst_avl_balanced_and_range():
    t = BinarySearchTree()
    for i in range(1024):
        t.insert(i, f"r{i}")
    assert t.height <= 11  # log2(1024)=10 -> AVL lo deja muy cerca
    assert t.range_query(10, 14) == ["r10", "r11", "r12", "r13", "r14"]
    t.insert(12, "r12b")
    assert t.search(12) == ["r12", "r12b"]
    assert t.remove_value(12, lambda v: v == "r12")
    assert t.remove_value(12, lambda v: v == "r12b")
    assert t.search(12) == []
    assert len(t.in_order()) == 1023


def test_graph_bfs_dfs_dijkstra():
    g = Graph()
    g.add_edge("A", "B", 1)
    g.add_edge("B", "D", 1)
    g.add_edge("A", "C", 2)
    g.add_edge("C", "D", 2)
    assert g.bfs_path("A", "D") in (["A", "B", "D"], ["A", "C", "D"])
    assert set(g.dfs_reachable("A")) == {"A", "B", "C", "D"}
    path, cost = g.dijkstra("A", "D")
    assert path == ["A", "B", "D"] and cost == 2
    # Si B es peligroso, la ruta segura lo evita
    path, _ = g.dijkstra("A", "D", penalty=lambda v: 10 if v == "B" else 0)
    assert path == ["A", "C", "D"]


def test_sorting_and_binary_search():
    data = [5, 3, 9, 1, 3, 7]
    assert merge_sort(data) == sorted(data)
    assert quick_sort(data, reverse=True) == sorted(data, reverse=True)
    pairs = [(1, "a"), (0, "b"), (1, "c")]
    assert merge_sort(pairs, key=lambda p: p[0], reverse=True) == [(1, "a"), (1, "c"), (0, "b")]
    names = sorted(["Chapinero", "Kennedy", "Suba", "Usaquen"])
    assert binary_search(names, "Suba") == 2
    assert binary_search(names, "Bosa") is None

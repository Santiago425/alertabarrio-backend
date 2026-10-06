"""
AlertEngine: aqui viven TODAS las estructuras de datos del sistema.

PostgreSQL es la fuente de verdad (lo que persiste), y al arrancar el
backend cargamos los datos en memoria dentro de nuestras estructuras para
atender rapido las operaciones del dia a dia:

    Estructura              | Para que la usamos
    ------------------------+-----------------------------------------------
    PriorityQueue (heap)    | Cola de moderacion: sale primero el mas grave
    HashTable -> Stack      | Historial de estados por reporte (deshacer)
    HashTable -> LinkedList | Feed de alertas activas por barrio
    HashTable -> LinkedList | Vecinos suscritos por barrio
    Queue (buffer circular) | Notificaciones pendientes por despachar (FIFO)
    BinarySearchTree (AVL)  | Historial de reportes ordenado por fecha
    Graph                   | Barrios conectados -> ruta mas segura
    DynamicArray + binsearch| Catalogo de barrios ordenado por nombre
    merge_sort / quick_sort | Feed general y ranking de barrios

Todas las operaciones se protegen con un Lock porque FastAPI atiende
peticiones en varios hilos.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..structures import (
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

ACTIVE_STATUSES = ("published", "verified")
PENDING_STATUSES = ("created",)


def ensure_aware(dt: datetime) -> datetime:
    """SQLite devuelve fechas sin zona horaria; las tratamos como UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass
class ReportItem:
    """Version liviana del reporte que guardamos dentro de las estructuras."""

    id: int
    title: str
    neighborhood_id: int
    user_id: int
    severity: int
    priority: float
    status: str
    created_at: datetime

    def short(self) -> dict:
        return {"id": self.id, "title": self.title, "priority": self.priority, "status": self.status}

    @staticmethod
    def from_model(r: models.Report) -> "ReportItem":
        return ReportItem(
            id=r.id,
            title=r.title,
            neighborhood_id=r.neighborhood_id,
            user_id=r.user_id,
            severity=r.incident_type.severity_level,
            priority=r.priority_score,
            status=r.status,
            created_at=ensure_aware(r.created_at),
        )


@dataclass
class StatusEntry:
    history_id: int
    previous_status: Optional[str]
    new_status: str
    changed_by: Optional[int]
    changed_at: datetime
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.history_id,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "changed_by": self.changed_by,
            "note": self.note,
            "changed_at": self.changed_at,
        }


@dataclass
class PendingNotification:
    user_id: int
    report_id: Optional[int]
    message: str
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def compute_priority(severity: int, zone_risk: Optional[float], has_photo: bool) -> float:
    """Prioridad del reporte en la cola de moderacion.
    La gravedad pesa mas; el riesgo que calcula la IA para esa zona/hora
    sube la prioridad; tener foto da un pequeno bono (mas confiable)."""
    score = severity * 20.0
    score += (zone_risk or 0.0) * 20.0
    if has_photo:
        score += 5.0
    return round(score, 2)


class AlertEngine:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        self.moderation_queue: PriorityQueue[ReportItem] = PriorityQueue(
            priority_of=lambda r: r.priority, id_of=lambda r: r.id
        )
        self.status_stacks: HashTable[int, Stack[StatusEntry]] = HashTable()
        self.zone_feeds: HashTable[int, LinkedList[ReportItem]] = HashTable()
        self.subscribers: HashTable[int, LinkedList[int]] = HashTable()
        self.notification_queue: Queue[PendingNotification] = Queue()
        self.timeline: BinarySearchTree[float, int] = BinarySearchTree()
        self.city_graph = Graph()
        self.neighborhood_catalog: DynamicArray[Tuple[str, int]] = DynamicArray()
        self.items: HashTable[int, ReportItem] = HashTable()  # id -> item
        self.dispatched_total = 0
        self.loaded = False

    # ================================================================ carga
    def load(self, db: Session) -> None:
        """Reconstruye todas las estructuras desde PostgreSQL."""
        with self.lock:
            self.reset()

            neighborhoods = db.scalars(select(models.Neighborhood)).all()
            for n in neighborhoods:
                self.city_graph.add_vertex(n.id, n.name)
            for c in db.scalars(select(models.NeighborhoodConnection)).all():
                self.city_graph.add_edge(c.from_neighborhood_id, c.to_neighborhood_id, c.distance_meters)
            # catalogo ordenado por nombre (merge sort) para busqueda binaria
            for name, nid in merge_sort([(n.name.lower(), n.id) for n in neighborhoods], key=lambda x: x[0]):
                self.neighborhood_catalog.append((name, nid))

            for s in db.scalars(select(models.Subscription).order_by(models.Subscription.id)).all():
                self.subscribers.get_or_create(s.neighborhood_id, LinkedList).push_back(s.user_id)

            reports = db.scalars(select(models.Report).order_by(models.Report.created_at, models.Report.id)).all()
            for r in reports:
                item = ReportItem.from_model(r)
                self.items.put(item.id, item)
                self.timeline.insert(item.created_at.timestamp(), item.id)
                if item.status in PENDING_STATUSES:
                    self.moderation_queue.push(item)
                elif item.status in ACTIVE_STATUSES:
                    # los reportes vienen en orden de fecha -> push_front deja el mas nuevo arriba
                    self.zone_feeds.get_or_create(item.neighborhood_id, LinkedList).push_front(item)

            history = db.scalars(
                select(models.ReportStatusHistory).order_by(
                    models.ReportStatusHistory.changed_at, models.ReportStatusHistory.id
                )
            ).all()
            for h in history:
                self.status_stacks.get_or_create(h.report_id, Stack).push(self._entry(h))
            self.loaded = True

    @staticmethod
    def _entry(h: models.ReportStatusHistory) -> StatusEntry:
        return StatusEntry(h.id, h.previous_status, h.new_status, h.changed_by, ensure_aware(h.changed_at), h.note)

    # ============================================================ reportes
    def add_report(self, item: ReportItem, first_status: models.ReportStatusHistory) -> int:
        """Nuevo reporte: entra a la cola de prioridad. Devuelve su posicion."""
        with self.lock:
            self.items.put(item.id, item)
            self.timeline.insert(item.created_at.timestamp(), item.id)
            self.status_stacks.get_or_create(item.id, Stack).push(self._entry(first_status))
            self.moderation_queue.push(item)
            order = [r.id for r in self.moderation_queue.ordered()]
            return order.index(item.id) + 1

    def get_item(self, report_id: int) -> Optional[ReportItem]:
        return self.items.get(report_id)

    def queue_order(self) -> List[ReportItem]:
        with self.lock:
            return self.moderation_queue.ordered()

    def take_next(self) -> Optional[ReportItem]:
        """El moderador pide el siguiente: sale el de MAYOR prioridad."""
        with self.lock:
            if self.moderation_queue.is_empty():
                return None
            return self.moderation_queue.pop()

    def take_specific(self, report_id: int) -> Optional[ReportItem]:
        with self.lock:
            return self.moderation_queue.remove(report_id)

    def push_status(self, report_id: int, history: models.ReportStatusHistory) -> None:
        with self.lock:
            item = self.items.get(report_id)
            if item is not None:
                item.status = history.new_status
            self.status_stacks.get_or_create(report_id, Stack).push(self._entry(history))

    def status_stack(self, report_id: int) -> List[StatusEntry]:
        with self.lock:
            stack = self.status_stacks.get(report_id)
            return stack.to_list() if stack else []

    def pop_status(self, report_id: int) -> Tuple[StatusEntry, StatusEntry]:
        """DESHACER: saca el tope de la pila. Devuelve (deshecho, nuevo_tope)."""
        with self.lock:
            stack = self.status_stacks.get(report_id)
            if stack is None or len(stack) <= 1:
                raise ValueError("No hay nada que deshacer: el reporte esta en su estado inicial")
            undone = stack.pop()
            current = stack.peek()
            item = self.items.get(report_id)
            if item is not None:
                item.status = current.new_status
            return undone, current

    def requeue(self, report_id: int) -> None:
        with self.lock:
            item = self.items.get(report_id)
            if item is not None:
                self.moderation_queue.push(item)

    # ================================================================ feed
    def publish(self, report_id: int, reporter_id: int, message: str) -> int:
        """Agrega al feed del barrio y encola notificaciones. Devuelve cuantas encolo."""
        with self.lock:
            item = self.items.get(report_id)
            if item is None:
                return 0
            feed = self.zone_feeds.get_or_create(item.neighborhood_id, LinkedList)
            if feed.find(lambda r: r.id == report_id) is None:
                feed.push_front(item)
            return self._notify_zone(item.neighborhood_id, report_id, message, exclude=reporter_id)

    def unpublish(self, report_id: int, message: Optional[str] = None) -> None:
        with self.lock:
            item = self.items.get(report_id)
            if item is None:
                return
            feed = self.zone_feeds.get(item.neighborhood_id)
            if feed is not None:
                feed.remove_first(lambda r: r.id == report_id)
            if message:
                self._notify_zone(item.neighborhood_id, report_id, message, exclude=None)

    def feed_ids(self, neighborhood_id: Optional[int], limit: int = 50) -> List[int]:
        with self.lock:
            if neighborhood_id is not None:
                feed = self.zone_feeds.get(neighborhood_id)
                return [r.id for r in feed.to_list(limit)] if feed else []
            # Feed general: juntamos todas las listas y ordenamos con merge sort
            # (estable) por prioridad y luego por fecha, de mayor a menor.
            everything: List[ReportItem] = []
            for _, feed in self.zone_feeds.items():
                everything.extend(feed)
            ordered = merge_sort(everything, key=lambda r: (r.priority, r.created_at.timestamp()), reverse=True)
            return [r.id for r in ordered[:limit]]

    def active_count_by_zone(self) -> Dict[int, int]:
        with self.lock:
            return {nid: len(feed) for nid, feed in self.zone_feeds.items()}

    def active_severity_by_zone(self) -> Dict[int, int]:
        with self.lock:
            return {nid: sum(r.severity for r in feed) for nid, feed in self.zone_feeds.items()}

    def ranking(self) -> List[Tuple[int, int]]:
        """Barrios ordenados por gravedad acumulada de alertas activas (quick sort)."""
        pairs = list(self.active_severity_by_zone().items())
        return quick_sort(pairs, key=lambda p: p[1], reverse=True)

    # ============================================================ timeline
    def range_ids(self, start: datetime, end: datetime) -> List[int]:
        with self.lock:
            return self.timeline.range_query(ensure_aware(start).timestamp(), ensure_aware(end).timestamp())

    # ===================================================== suscripciones
    def subscribe(self, neighborhood_id: int, user_id: int) -> None:
        with self.lock:
            subs = self.subscribers.get_or_create(neighborhood_id, LinkedList)
            if subs.find(lambda u: u == user_id) is None:
                subs.push_back(user_id)

    def unsubscribe(self, neighborhood_id: int, user_id: int) -> None:
        with self.lock:
            subs = self.subscribers.get(neighborhood_id)
            if subs is not None:
                subs.remove_first(lambda u: u == user_id)

    def subscriber_count(self, neighborhood_id: int) -> int:
        subs = self.subscribers.get(neighborhood_id)
        return len(subs) if subs else 0

    # ===================================================== notificaciones
    def _notify_zone(self, neighborhood_id: int, report_id: int, message: str, exclude: Optional[int]) -> int:
        subs = self.subscribers.get(neighborhood_id)
        count = 0
        if subs is None:
            return 0
        for user_id in subs:
            if user_id == exclude:
                continue
            self.notification_queue.enqueue(PendingNotification(user_id, report_id, message))
            count += 1
        return count

    def drain_notifications(self, max_items: int = 500) -> List[PendingNotification]:
        """Saca de la cola (FIFO) las notificaciones pendientes para guardarlas."""
        with self.lock:
            out: List[PendingNotification] = []
            while not self.notification_queue.is_empty() and len(out) < max_items:
                out.append(self.notification_queue.dequeue())
            self.dispatched_total += len(out)
            return out

    # ================================================================ grafo
    def find_neighborhood(self, name: str) -> Optional[int]:
        catalog = self.neighborhood_catalog.to_list()
        idx = binary_search(catalog, name.strip().lower(), key=lambda x: x[0])
        return catalog[idx][1] if idx is not None else None

    # ============================================================ snapshot
    def snapshot(self) -> dict:
        """Estado interno de todas las estructuras (para la exposicion)."""
        with self.lock:
            some_stacks = {}
            for rid, stack in self.status_stacks.items():
                if len(stack) > 1:
                    some_stacks[rid] = [e.new_status for e in stack]
                if len(some_stacks) >= 8:
                    break
            return {
                "priority_queue": self.moderation_queue.snapshot(lambda r: r.short()),
                "status_stacks": {
                    "type": "HashTable<report_id, Stack>",
                    "reports_with_history": len(self.status_stacks),
                    "examples_top_to_bottom": some_stacks,
                },
                "zone_feeds": {
                    "type": "HashTable<neighborhood_id, LinkedList>",
                    "table": {
                        "buckets": self.zone_feeds.snapshot()["buckets"],
                        "load_factor": round(self.zone_feeds.load_factor, 3),
                    },
                    "feeds": {
                        self.city_graph.label(nid): [r.short() for r in feed.to_list(10)]
                        for nid, feed in self.zone_feeds.items()
                    },
                },
                "subscribers": {
                    self.city_graph.label(nid): subs.to_list() for nid, subs in self.subscribers.items()
                },
                "notification_queue": self.notification_queue.snapshot(
                    lambda n: {"user_id": n.user_id, "report_id": n.report_id}
                ),
                "notifications_dispatched": self.dispatched_total,
                "timeline_bst": self.timeline.snapshot(
                    key_mapper=lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
                ),
                "city_graph": self.city_graph.snapshot(),
                "neighborhood_catalog": self.neighborhood_catalog.snapshot(lambda x: x[0]),
                "ranking_quick_sort": [
                    {"neighborhood": self.city_graph.label(nid), "active_severity": sev}
                    for nid, sev in self.ranking()
                ],
            }


# Instancia unica que comparte toda la aplicacion
engine = AlertEngine()

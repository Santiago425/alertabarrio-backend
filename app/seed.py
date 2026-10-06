"""
Datos de ejemplo para que el sistema arranque con informacion realista:
barrios de Bogota, sus conexiones (grafo), tipos de incidente, usuarios de
prueba y ~3 meses de reportes historicos con PATRONES (por ejemplo, robos
en Chapinero los jueves y viernes en la noche) para que la IA los detecte.

Se ejecuta solo si la base de datos esta vacia.
Uso manual:  python -m app.seed
"""

import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import get_settings
from .database import Base, SessionLocal, engine as db_engine
from .security import hash_password

DEMO_PASSWORD = "Alerta2026*"

NEIGHBORHOODS = [
    ("Chapinero", 4.6486, -74.0628),
    ("Usaquen", 4.6940, -74.0310),
    ("Teusaquillo", 4.6380, -74.0790),
    ("Barrios Unidos", 4.6670, -74.0750),
    ("Suba", 4.7410, -74.0840),
    ("Engativa", 4.7080, -74.1100),
    ("Fontibon", 4.6780, -74.1450),
    ("Kennedy", 4.6280, -74.1580),
    ("Puente Aranda", 4.6150, -74.1170),
    ("Los Martires", 4.6050, -74.0900),
    ("Santa Fe", 4.6100, -74.0680),
    ("La Candelaria", 4.5970, -74.0740),
    ("Antonio Narino", 4.5880, -74.1000),
    ("Bosa", 4.6180, -74.1900),
]

CONNECTIONS = [
    ("Usaquen", "Chapinero", "Carrera 7"),
    ("Usaquen", "Suba", "Calle 170"),
    ("Chapinero", "Barrios Unidos", "Avenida Caracas"),
    ("Chapinero", "Teusaquillo", "Calle 45"),
    ("Chapinero", "Santa Fe", "Carrera 7"),
    ("Suba", "Barrios Unidos", "Autopista Norte"),
    ("Suba", "Engativa", "Avenida Ciudad de Cali"),
    ("Barrios Unidos", "Teusaquillo", "Avenida NQS"),
    ("Barrios Unidos", "Engativa", "Calle 80"),
    ("Engativa", "Fontibon", "Avenida Boyaca"),
    ("Engativa", "Teusaquillo", "Calle 26"),
    ("Teusaquillo", "Puente Aranda", "Avenida de las Americas"),
    ("Teusaquillo", "Los Martires", "Avenida Caracas"),
    ("Fontibon", "Kennedy", "Avenida Boyaca"),
    ("Fontibon", "Puente Aranda", "Calle 13"),
    ("Kennedy", "Puente Aranda", "Avenida de las Americas"),
    ("Kennedy", "Bosa", "Autopista Sur"),
    ("Puente Aranda", "Los Martires", "Calle 13"),
    ("Puente Aranda", "Antonio Narino", "Avenida NQS"),
    ("Los Martires", "Santa Fe", "Avenida Jimenez"),
    ("Los Martires", "Antonio Narino", "Avenida Caracas"),
    ("Santa Fe", "La Candelaria", "Carrera 7"),
    ("La Candelaria", "Antonio Narino", "Avenida Comuneros"),
]

INCIDENT_TYPES = [
    ("armed_robbery", "Robo armado", 5, "#b91c1c"),
    ("assault", "Agresion o rina", 4, "#dc2626"),
    ("home_burglary", "Robo a vivienda", 4, "#ea580c"),
    ("vehicle_theft", "Robo de vehiculo", 4, "#f97316"),
    ("theft", "Hurto", 3, "#f59e0b"),
    ("drug_dealing", "Expendio de drogas", 3, "#9333ea"),
    ("vandalism", "Vandalismo", 2, "#2563eb"),
    ("suspicious_activity", "Actividad sospechosa", 2, "#64748b"),
]

TEXTS = {
    "armed_robbery": [
        ("Atraco con arma blanca", "Dos hombres en moto me amenazaron con cuchillo y se llevaron el celular."),
        ("Robo con pistola en la esquina", "Un sujeto armado con pistola robo a una pareja que salia del restaurante."),
        ("Asalto a mano armada", "Atracaron a un domiciliario con arma de fuego y le quitaron la moto."),
    ],
    "assault": [
        ("Rina en la salida del bar", "Varias personas se agarraron a golpes, hay un herido."),
        ("Agresion a un vecino", "Un hombre golpeo a un vecino en el parque, llamamos a la policia."),
    ],
    "home_burglary": [
        ("Se metieron a una casa", "Forzaron la puerta y se llevaron el televisor y un computador."),
        ("Robo en apartamento", "Entraron por la ventana del primer piso mientras la familia dormia."),
    ],
    "vehicle_theft": [
        ("Se robaron un carro", "Hurtaron un carro parqueado en la calle, rompieron el vidrio."),
        ("Robo de moto", "Se llevaron una moto que estaba frente a la panaderia."),
    ],
    "theft": [
        ("Raponazo de celular", "Le arrebataron el celular a una senora en el paradero del bus."),
        ("Hurto en el transporte", "En el bus le sacaron la billetera del bolsillo a un estudiante."),
        ("Cosquilleo en el centro comercial", "Le robaron el bolso a una mujer sin que se diera cuenta."),
    ],
    "drug_dealing": [
        ("Venta de droga en el parque", "Todas las noches hay personas vendiendo droga cerca a los columpios."),
        ("Olla en la cuadra", "Hay mucho movimiento de gente comprando sustancias en una casa."),
    ],
    "vandalism": [
        ("Danaron el alumbrado", "Rompieron las lamparas del parque y quedo totalmente oscuro."),
        ("Grafitis y vidrios rotos", "Rayaron las paredes del colegio y rompieron vidrios."),
    ],
    "suspicious_activity": [
        ("Persona sospechosa mirando casas", "Un hombre lleva varias horas mirando las casas y tomando fotos."),
        ("Carro sospechoso estacionado", "Un carro sin placas lleva rato parqueado con dos personas adentro."),
    ],
}

# (barrio, tipos, dias_semana, franjas_horarias, peso) -> patrones que la IA debe encontrar
PATTERNS = [
    ("Chapinero", ["armed_robbery", "theft"], [3, 4], [19, 20, 21, 22, 23], 40),  # jueves/viernes noche
    ("Kennedy", ["theft", "assault"], [5, 6], [13, 14, 15, 16, 17], 14),  # fin de semana tarde
    ("Santa Fe", ["theft", "drug_dealing"], [0, 1, 2, 3, 4], [9, 10, 11, 12], 14),  # entre semana manana
    ("Suba", ["home_burglary", "vehicle_theft"], [0, 1, 2, 3, 4, 5, 6], [1, 2, 3, 4], 12),  # madrugada
    ("La Candelaria", ["theft"], [4, 5], [18, 19, 20], 8),
    ("Bosa", ["assault", "drug_dealing"], [4, 5], [21, 22, 23], 8),
]


def _distance_m(a, b) -> float:
    """Distancia aproximada (haversine) * 1.3 porque las calles no son rectas."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(h)) * 1.3, 0)


def seed(db: Session) -> bool:
    if db.scalar(select(models.Role).limit(1)) is not None:
        return False  # ya tiene datos

    rng = random.Random(2026)
    tz = ZoneInfo(get_settings().timezone)
    now = datetime.now(timezone.utc)

    roles = {
        name: models.Role(name=name, description=desc)
        for name, desc in [
            ("citizen", "Vecino que reporta y confirma alertas"),
            ("moderator", "Revisa, publica o rechaza reportes"),
            ("admin", "Administrador del sistema"),
        ]
    }
    db.add_all(roles.values())

    hoods = {name: models.Neighborhood(name=name, city="Bogota", latitude=lat, longitude=lon) for name, lat, lon in NEIGHBORHOODS}
    db.add_all(hoods.values())
    db.flush()

    for a, b, road in CONNECTIONS:
        ha, hb = hoods[a], hoods[b]
        db.add(
            models.NeighborhoodConnection(
                from_neighborhood_id=ha.id,
                to_neighborhood_id=hb.id,
                distance_meters=_distance_m((ha.latitude, ha.longitude), (hb.latitude, hb.longitude)),
                road_name=road,
            )
        )

    types = {code: models.IncidentType(code=code, name=name, severity_level=sev, color=color) for code, name, sev, color in INCIDENT_TYPES}
    db.add_all(types.values())

    pwd = hash_password(DEMO_PASSWORD)
    users_data = [
        ("Administrador AlertaBarrio", "admin@alertabarrio.co", "admin", None),
        ("Moderador Central", "moderador@alertabarrio.co", "moderator", "Chapinero"),
        ("Ana Rodriguez", "ana@alertabarrio.co", "citizen", "Chapinero"),
        ("Carlos Gomez", "carlos@alertabarrio.co", "citizen", "Chapinero"),
        ("Laura Martinez", "laura@alertabarrio.co", "citizen", "Kennedy"),
        ("Pedro Sanchez", "pedro@alertabarrio.co", "citizen", "Suba"),
        ("Valentina Ruiz", "valentina@alertabarrio.co", "citizen", "Santa Fe"),
        ("Jorge Herrera", "jorge@alertabarrio.co", "citizen", "Teusaquillo"),
    ]
    users = []
    for full_name, email, role, hood in users_data:
        u = models.User(
            full_name=full_name,
            email=email,
            password_hash=pwd,
            phone=f"300{rng.randint(1000000, 9999999)}",
            role=roles[role],
            neighborhood=hoods[hood] if hood else None,
        )
        users.append(u)
    db.add_all(users)
    db.flush()
    citizens = [u for u in users if u.role.name == "citizen"]
    moderator = users[1]

    # Suscripciones: cada vecino a su barrio + algunos barrios extra
    subs = {(u.id, u.neighborhood.id) for u in citizens}
    subs |= {(citizens[0].id, hoods["Teusaquillo"].id), (citizens[1].id, hoods["Santa Fe"].id), (citizens[5].id, hoods["Chapinero"].id)}
    subs |= {(moderator.id, hoods["Chapinero"].id)}
    for uid, nid in subs:
        db.add(models.Subscription(user_id=uid, neighborhood_id=nid))

    # -------------------------------------------------- reportes historicos
    def random_moment(days_back_max: int, weekdays, hours) -> datetime:
        while True:
            d = now.astimezone(tz) - timedelta(days=rng.randint(1, days_back_max))
            if d.weekday() in weekdays:
                local = d.replace(hour=rng.choice(hours), minute=rng.randint(0, 59), second=0, microsecond=0)
                return local.astimezone(timezone.utc)

    plan = []
    for hood, codes, days, hours, count in PATTERNS:
        for _ in range(count):
            plan.append((hood, rng.choice(codes), random_moment(90, days, hours)))
    # ruido: reportes al azar en toda la ciudad
    for _ in range(45):
        hood = rng.choice(NEIGHBORHOODS)[0]
        code = rng.choice(list(TEXTS.keys()))
        plan.append((hood, code, random_moment(90, range(7), list(range(24)))))
    # reportes de HOY (para el resumen diario) y pendientes de moderar
    recent = [
        ("Chapinero", "armed_robbery", 1, "published"),
        ("Chapinero", "theft", 3, "verified"),
        ("Chapinero", "suspicious_activity", 5, "published"),
        ("Kennedy", "assault", 2, "published"),
        ("Santa Fe", "theft", 4, "published"),
        ("Chapinero", "theft", 0.5, "created"),
        ("Suba", "home_burglary", 0.8, "created"),
        ("Teusaquillo", "suspicious_activity", 0.3, "created"),
        ("Kennedy", "armed_robbery", 0.2, "created"),
        ("Bosa", "vandalism", 0.6, "created"),
        ("Engativa", "vehicle_theft", 1.5, "in_review"),
    ]

    def make_report(hood_name, code, occurred, status_target):
        hood = hoods[hood_name]
        it = types[code]
        title, desc = rng.choice(TEXTS[code])
        reporter = rng.choice(citizens)
        created = occurred + timedelta(minutes=rng.randint(3, 40))
        if created > now:
            created = now - timedelta(minutes=1)
        r = models.Report(
            user_id=reporter.id,
            neighborhood_id=hood.id,
            incident_type_id=it.id,
            title=title,
            description=desc,
            latitude=hood.latitude + rng.gauss(0, 0.004),
            longitude=hood.longitude + rng.gauss(0, 0.004),
            occurred_at=occurred,
            status=status_target,
            priority_score=it.severity_level * 20.0,
            created_at=created,
            updated_at=created,
        )
        db.add(r)
        db.flush()
        # Historial de estados (la PILA) coherente con el estado final
        path = {
            "created": ["created"],
            "in_review": ["created", "in_review"],
            "published": ["created", "in_review", "published"],
            "verified": ["created", "in_review", "published", "verified"],
            "rejected": ["created", "in_review", "rejected"],
        }[status_target]
        t = created
        prev = None
        for st in path:
            db.add(
                models.ReportStatusHistory(
                    report_id=r.id,
                    previous_status=prev,
                    new_status=st,
                    changed_by=reporter.id if st == "created" else moderator.id,
                    note="Reporte creado" if st == "created" else None,
                    changed_at=t,
                )
            )
            prev = st
            t = min(t + timedelta(minutes=rng.randint(5, 50)), now)
        if status_target == "verified":
            others = [c for c in citizens if c.id != reporter.id]
            for v in rng.sample(others, 2):
                db.add(models.ReportVerification(report_id=r.id, user_id=v.id, is_confirmed=True))
        return r

    plan.sort(key=lambda p: p[2])
    for hood_name, code, occurred in plan:
        status_target = rng.choices(["published", "verified", "rejected"], weights=[55, 35, 10])[0]
        make_report(hood_name, code, occurred, status_target)
    last = None
    for hood_name, code, hours_ago, status_target in recent:
        last = make_report(hood_name, code, now - timedelta(hours=hours_ago), status_target)

    ana = citizens[0]
    for msg in [
        "Nueva alerta en Chapinero: Robo armado - Atraco con arma blanca",
        "Nueva alerta en Chapinero: Hurto - Raponazo de celular",
    ]:
        db.add(models.Notification(user_id=ana.id, report_id=last.id if last else None, message=msg))

    db.commit()
    return True


def init_db(with_seed: bool = True) -> None:
    Base.metadata.create_all(bind=db_engine)
    if with_seed:
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()


if __name__ == "__main__":
    init_db(True)
    print("Base de datos creada y con datos de ejemplo.")

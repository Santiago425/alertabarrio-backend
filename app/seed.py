"""
Datos de ejemplo para que el sistema arranque con informacion realista:
barrios de Pasto, sus conexiones (grafo), tipos de incidente, usuarios de
prueba y ~3 meses de reportes historicos con PATRONES (por ejemplo, robos
en el Centro los jueves y viernes en la noche) para que la IA los detecte.

Se ejecuta solo si la base de datos esta vacia.
Uso manual:  python -m app.seed
"""

import math
import random
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session

from . import models
from .barrios_pasto import BARRIOS
from .config import get_settings
from .database import Base, SessionLocal, engine as db_engine
from .security import hash_password


CITY = get_settings().city

# Barrios de San Juan de Pasto (coordenadas aproximadas del centro de cada barrio)
NEIGHBORHOODS = [
    ("Centro", 1.2136, -77.2811),
    ("Pandiaco", 1.2295, -77.2862),
    ("Las Cuadras", 1.2188, -77.2783),
    ("Palermo", 1.2236, -77.2742),
    ("Torobajo", 1.2318, -77.2927),
    ("Anganoy", 1.2163, -77.2985),
    ("Mijitayo", 1.2068, -77.2925),
    ("Lorenzo de Aldana", 1.1968, -77.2728),
    ("Chapultepec", 1.2022, -77.2838),
    ("Obrero", 1.2085, -77.2762),
    ("Potrerillo", 1.2028, -77.2693),
    ("San Felipe", 1.2167, -77.2848),
    ("Santa Monica", 1.2118, -77.2668),
    ("El Tejar", 1.2052, -77.2603),
]

CONNECTIONS = [
    ("Pandiaco", "Torobajo", "Avenida Panamericana"),
    ("Pandiaco", "Palermo", "Avenida de los Estudiantes"),
    ("Pandiaco", "Las Cuadras", "Carrera 27"),
    ("Torobajo", "Anganoy", "Avenida Panamericana"),
    ("Torobajo", "San Felipe", "Calle 22"),
    ("Palermo", "Las Cuadras", "Calle 20"),
    ("Palermo", "Santa Monica", "Avenida Panamericana"),
    ("Las Cuadras", "Centro", "Carrera 25"),
    ("Las Cuadras", "San Felipe", "Carrera 24"),
    ("San Felipe", "Centro", "Calle 18"),
    ("San Felipe", "Anganoy", "Calle 18"),
    ("Anganoy", "Mijitayo", "Avenida Mijitayo"),
    ("Mijitayo", "Chapultepec", "Avenida Idema"),
    ("Chapultepec", "Centro", "Carrera 27"),
    ("Chapultepec", "Obrero", "Carrera 22"),
    ("Chapultepec", "Lorenzo de Aldana", "Avenida Panamericana"),
    ("Centro", "Obrero", "Avenida Boyaca"),
    ("Centro", "Santa Monica", "Calle 19"),
    ("Obrero", "Potrerillo", "Calle 16"),
    ("Potrerillo", "Lorenzo de Aldana", "Avenida Chile"),
    ("Potrerillo", "El Tejar", "Avenida Julian Bucheli"),
    ("Santa Monica", "El Tejar", "Avenida Santander"),
    ("Santa Monica", "Potrerillo", "Carrera 16"),
]

# Base de datos creada con la version de Bogota -> barrio equivalente en Pasto
# (mismo id, asi los usuarios y reportes que ya existen se conservan).
BOGOTA_TO_PASTO = {
    "Chapinero": "Centro",
    "Usaquen": "Pandiaco",
    "Teusaquillo": "Las Cuadras",
    "Barrios Unidos": "Palermo",
    "Suba": "Torobajo",
    "Engativa": "Anganoy",
    "Fontibon": "Mijitayo",
    "Kennedy": "Lorenzo de Aldana",
    "Puente Aranda": "Chapultepec",
    "Los Martires": "Obrero",
    "Santa Fe": "Potrerillo",
    "La Candelaria": "San Felipe",
    "Antonio Narino": "Santa Monica",
    "Bosa": "El Tejar",
}

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

# Cuanto dura cada tipo de alerta en el mapa (minutos) si el administrador no lo ha cambiado.
# Al vencer, la alerta sale del mapa pero queda en el historial y en las estadisticas.
DEFAULT_DURATIONS = {
    "armed_robbery": 6 * 60,
    "assault": 3 * 60,
    "home_burglary": 12 * 60,
    "vehicle_theft": 12 * 60,
    "theft": 4 * 60,
    "drug_dealing": 3 * 24 * 60,
    "vandalism": 24 * 60,
    "suspicious_activity": 2 * 60,
}
DEFAULT_DURATION = 24 * 60

# Categorias para agrupar los tipos (en el reporte y en Configuracion de alertas)
CATEGORIES = ["Seguridad", "Tránsito", "Emergencias", "Servicios públicos", "Convivencia", "Otros"]
BASE_CATEGORY = {
    "armed_robbery": "Seguridad",
    "assault": "Seguridad",
    "home_burglary": "Seguridad",
    "vehicle_theft": "Seguridad",
    "theft": "Seguridad",
    "drug_dealing": "Seguridad",
    "suspicious_activity": "Seguridad",
    "vandalism": "Convivencia",
}

# Catalogo completo (el profe pidio mas tipos). Referencia: Codigo de Policia (Ley 1801),
# categorias de la Policia Nacional y la Linea 123.
# (codigo, nombre, gravedad 1-5, color, minutos en el mapa, categoria)
EXTRA_INCIDENT_TYPES = [
    # Seguridad
    ("business_robbery", "Hurto a comercio", 4, "#c2410c", 6 * 60, "Seguridad"),
    ("bike_theft", "Hurto de bicicleta", 3, "#d97706", 12 * 60, "Seguridad"),
    ("gunshots", "Disparos", 5, "#7f1d1d", 3 * 60, "Seguridad"),
    ("homicide", "Homicidio", 5, "#450a0a", 24 * 60, "Seguridad"),
    ("extortion", "Extorsión", 5, "#9f1239", 24 * 60, "Seguridad"),
    ("sexual_harassment", "Acoso o abuso sexual", 5, "#db2777", 12 * 60, "Seguridad"),
    ("domestic_violence", "Violencia intrafamiliar", 5, "#be123c", 12 * 60, "Seguridad"),
    ("child_abuse", "Maltrato infantil", 5, "#e11d48", 12 * 60, "Seguridad"),
    ("missing_person", "Persona desaparecida", 5, "#7c3aed", 3 * 24 * 60, "Seguridad"),
    ("gang_activity", "Pandillas", 4, "#581c87", 24 * 60, "Seguridad"),
    ("scam", "Estafa", 2, "#a16207", 24 * 60, "Seguridad"),
    # Transito
    ("traffic_accident", "Accidente de tránsito", 3, "#0284c7", 90, "Tránsito"),
    ("motorcycle_accident", "Accidente de moto", 3, "#0ea5e9", 60, "Tránsito"),
    ("pedestrian_hit", "Atropello", 4, "#0369a1", 2 * 60, "Tránsito"),
    ("drunk_driving", "Conductor ebrio", 4, "#1d4ed8", 60, "Tránsito"),
    ("illegal_racing", "Piques ilegales", 3, "#4338ca", 2 * 60, "Tránsito"),
    ("road_blocked", "Vía bloqueada o trancón", 2, "#78716c", 2 * 60, "Tránsito"),
    ("traffic_light_failure", "Semáforo dañado", 2, "#57534e", 12 * 60, "Tránsito"),
    ("pothole", "Hueco en la vía", 1, "#a8a29e", 7 * 24 * 60, "Tránsito"),
    ("abandoned_vehicle", "Vehículo abandonado", 1, "#94a3b8", 3 * 24 * 60, "Tránsito"),
    # Emergencias
    ("medical_emergency", "Emergencia médica", 4, "#10b981", 60, "Emergencias"),
    ("fire", "Incendio", 5, "#f43f5e", 4 * 60, "Emergencias"),
    ("gas_leak", "Fuga de gas", 5, "#fb7185", 3 * 60, "Emergencias"),
    ("flood", "Inundación", 4, "#0891b2", 6 * 60, "Emergencias"),
    ("landslide", "Deslizamiento", 4, "#92400e", 24 * 60, "Emergencias"),
    ("earthquake", "Sismo", 5, "#78350f", 6 * 60, "Emergencias"),
    ("volcanic_activity", "Actividad del volcán Galeras", 4, "#b45309", 24 * 60, "Emergencias"),
    ("fallen_power_line", "Cable eléctrico caído", 4, "#facc15", 6 * 60, "Emergencias"),
    ("fallen_tree", "Árbol caído", 2, "#15803d", 6 * 60, "Emergencias"),
    # Servicios publicos
    ("streetlight_failure", "Falla de alumbrado", 1, "#eab308", 3 * 24 * 60, "Servicios públicos"),
    ("power_outage", "Corte de luz", 2, "#ca8a04", 6 * 60, "Servicios públicos"),
    ("water_outage", "Corte de agua", 2, "#06b6d4", 12 * 60, "Servicios públicos"),
    ("open_sewer", "Alcantarilla destapada", 3, "#475569", 3 * 24 * 60, "Servicios públicos"),
    ("garbage", "Basuras acumuladas", 1, "#4d7c0f", 3 * 24 * 60, "Servicios públicos"),
    # Convivencia
    ("excessive_noise", "Ruido excesivo", 1, "#6366f1", 3 * 60, "Convivencia"),
    ("public_drug_use", "Consumo de sustancias en vía pública", 2, "#a855f7", 4 * 60, "Convivencia"),
    ("public_drinking", "Consumo de alcohol en vía pública", 1, "#8b5cf6", 3 * 60, "Convivencia"),
    ("fireworks", "Pólvora", 3, "#f97316", 3 * 60, "Convivencia"),
    ("dangerous_animal", "Animal peligroso", 3, "#65a30d", 3 * 60, "Convivencia"),
    ("animal_abuse", "Maltrato animal", 3, "#84cc16", 24 * 60, "Convivencia"),
    ("public_space_invasion", "Invasión del espacio público", 1, "#64748b", 24 * 60, "Convivencia"),
    # Otros: para lo que no este en la lista
    ("other", "Otro (no está en la lista)", 2, "#334155", 4 * 60, "Otros"),
]
CATALOG_CODES = set(BASE_CATEGORY) | {c for c, *_ in EXTRA_INCIDENT_TYPES}

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
    ("Centro", ["armed_robbery", "theft"], [3, 4], [19, 20, 21, 22, 23], 40),  # jueves/viernes noche
    ("Lorenzo de Aldana", ["theft", "assault"], [5, 6], [13, 14, 15, 16, 17], 14),  # fin de semana tarde
    ("Potrerillo", ["theft", "drug_dealing"], [0, 1, 2, 3, 4], [9, 10, 11, 12], 14),  # entre semana manana
    ("Torobajo", ["home_burglary", "vehicle_theft"], [0, 1, 2, 3, 4, 5, 6], [1, 2, 3, 4], 12),  # madrugada
    ("San Felipe", ["theft"], [4, 5], [18, 19, 20], 8),
    ("El Tejar", ["assault", "drug_dealing"], [4, 5], [21, 22, 23], 8),
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

    hoods = {name: models.Neighborhood(name=name, city=CITY, latitude=lat, longitude=lon) for name, lat, lon in NEIGHBORHOODS}
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

    types = {
        code: models.IncidentType(
            code=code, name=name, severity_level=sev, color=color, duration_minutes=DEFAULT_DURATIONS.get(code, DEFAULT_DURATION)
        )
        for code, name, sev, color in INCIDENT_TYPES
    }
    db.add_all(types.values())

    pwd = hash_password(get_settings().demo_password)
    users_data = [
        ("Administrador AlertaBarrio", "admin@alertabarrio.co", "admin", None),
        ("Moderador Central", "moderador@alertabarrio.co", "moderator", "Centro"),
        ("Ana Rodriguez", "ana@alertabarrio.co", "citizen", "Centro"),
        ("Carlos Gomez", "carlos@alertabarrio.co", "citizen", "Centro"),
        ("Laura Martinez", "laura@alertabarrio.co", "citizen", "Lorenzo de Aldana"),
        ("Pedro Sanchez", "pedro@alertabarrio.co", "citizen", "Torobajo"),
        ("Valentina Ruiz", "valentina@alertabarrio.co", "citizen", "Potrerillo"),
        ("Jorge Herrera", "jorge@alertabarrio.co", "citizen", "Las Cuadras"),
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
    subs |= {(citizens[0].id, hoods["Las Cuadras"].id), (citizens[1].id, hoods["Potrerillo"].id), (citizens[5].id, hoods["Centro"].id)}
    subs |= {(moderator.id, hoods["Centro"].id)}
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
        ("Centro", "armed_robbery", 1, "published"),
        ("Centro", "theft", 3, "verified"),
        ("Centro", "suspicious_activity", 5, "published"),
        ("Lorenzo de Aldana", "assault", 2, "published"),
        ("Potrerillo", "theft", 4, "published"),
        ("Centro", "theft", 0.5, "created"),
        ("Torobajo", "home_burglary", 0.8, "created"),
        ("Las Cuadras", "suspicious_activity", 0.3, "created"),
        ("Lorenzo de Aldana", "armed_robbery", 0.2, "created"),
        ("El Tejar", "vandalism", 0.6, "created"),
        ("Anganoy", "vehicle_theft", 1.5, "in_review"),
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
            latitude=hood.latitude + rng.gauss(0, 0.0018),
            longitude=hood.longitude + rng.gauss(0, 0.0018),
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
        "Nueva alerta en Centro: Robo armado - Atraco con arma blanca",
        "Nueva alerta en Centro: Hurto - Raponazo de celular",
    ]:
        db.add(models.Notification(user_id=ana.id, report_id=last.id if last else None, message=msg))

    db.commit()
    return True


def migrate_to_pasto(db: Session) -> bool:
    """
    Pasa una base creada con los barrios de Bogota a los barrios de Pasto.

    No borra nada: cada barrio conserva su id (usuarios, suscripciones y
    reportes siguen apuntando al mismo), solo cambia nombre, ciudad y
    coordenadas. Los reportes se mueven junto con su barrio y las vias del
    grafo se reemplazan por las de Pasto. Si ya esta en Pasto no hace nada.
    """
    old = db.scalars(select(models.Neighborhood).where(models.Neighborhood.city == "Bogota")).all()
    if not old:
        return False

    coords = {name: (lat, lon) for name, lat, lon in NEIGHBORHOODS}
    moved = {}
    for hood in old:
        new_name = BOGOTA_TO_PASTO.get(hood.name)
        if new_name is None:
            hood.city = CITY  # barrio agregado a mano: solo cambiamos la ciudad
            continue
        lat, lon = coords[new_name]
        for r in db.scalars(select(models.Report).where(models.Report.neighborhood_id == hood.id)):
            # mantenemos la posicion relativa al centro del barrio, pero mas cerca
            # porque los barrios de Pasto son mas pequenos que las localidades de Bogota
            r.latitude = lat + (r.latitude - hood.latitude) * 0.45
            r.longitude = lon + (r.longitude - hood.longitude) * 0.45
        moved[hood.name] = new_name
        hood.name, hood.city, hood.latitude, hood.longitude = new_name, CITY, lat, lon
    db.flush()

    hoods = {h.name: h for h in db.scalars(select(models.Neighborhood))}
    db.execute(delete(models.NeighborhoodConnection))
    for a, b, road in CONNECTIONS:
        if a in hoods and b in hoods:
            ha, hb = hoods[a], hoods[b]
            db.add(
                models.NeighborhoodConnection(
                    from_neighborhood_id=ha.id,
                    to_neighborhood_id=hb.id,
                    distance_meters=_distance_m((ha.latitude, ha.longitude), (hb.latitude, hb.longitude)),
                    road_name=road,
                )
            )

    # Textos guardados que nombran los barrios viejos
    for n in db.scalars(select(models.Notification)):
        for a, b in moved.items():
            n.message = n.message.replace(f" en {a}:", f" en {b}:")
    # Los resumenes y el riesgo se vuelven a calcular con los barrios nuevos
    db.execute(delete(models.DailySummary))
    db.execute(delete(models.RiskHotspot))
    db.commit()
    return True


# Columnas que se agregaron despues de crear las tablas en produccion
NEW_COLUMNS = {
    "users": {
        "token_version": "INTEGER NOT NULL DEFAULT 0",
        "totp_secret": "VARCHAR(64)",
        "totp_enabled": "BOOLEAN NOT NULL DEFAULT false",
        "last_login_at": "TIMESTAMP WITH TIME ZONE",
    },
    "neighborhoods": {"comuna": "INTEGER"},
    "reports": {"address": "VARCHAR(200)", "published_at": "TIMESTAMP WITH TIME ZONE"},
    "incident_types": {
        "duration_minutes": "INTEGER",
        "is_active": "BOOLEAN NOT NULL DEFAULT true",
        "category": "VARCHAR(40)",
    },
}


def add_missing_columns() -> None:
    """create_all no altera tablas existentes: agregamos a mano las columnas nuevas."""
    inspector = inspect(db_engine)
    with db_engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    if db_engine.dialect.name == "sqlite":
                        ddl = ddl.replace("TIMESTAMP WITH TIME ZONE", "DATETIME").replace("DEFAULT false", "DEFAULT 0")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _norm(name: str) -> str:
    """Minusculas y sin tildes: 'Santa Mónica' y 'Santa Monica' son el mismo barrio."""
    return "".join(c for c in unicodedata.normalize("NFD", name.lower()) if unicodedata.category(c) != "Mn").strip()


def sync_pasto_barrios(db: Session) -> int:
    """
    Agrega los barrios de Pasto que falten (lista completa por comuna en
    barrios_pasto.py) y conecta cada barrio nuevo con sus vecinos en el grafo.

    No borra nada y conserva los ids. Si un barrio que ya existia cambia de
    punto (para quedar dentro de su comuna), sus reportes se corren con el.
    Devuelve cuantos barrios agrego; si ya esta todo, no hace nada.
    """
    hoods = db.scalars(select(models.Neighborhood)).all()
    by_norm = {_norm(h.name): h for h in hoods}
    if all(_norm(n) in by_norm and by_norm[_norm(n)].comuna == k for n, k, _, _ in BARRIOS):
        return 0

    added = []
    for name, comuna, lat, lon in BARRIOS:
        hood = by_norm.get(_norm(name))
        if hood is None:
            hood = models.Neighborhood(name=name, city=CITY, comuna=comuna, latitude=lat, longitude=lon)
            db.add(hood)
            by_norm[_norm(name)] = hood
            added.append(hood)
            continue
        if hood.comuna is None and (hood.latitude, hood.longitude) != (lat, lon):
            dlat, dlon = lat - hood.latitude, lon - hood.longitude
            for r in db.scalars(select(models.Report).where(models.Report.neighborhood_id == hood.id)):
                r.latitude += dlat
                r.longitude += dlon
            hood.latitude, hood.longitude = lat, lon
        hood.comuna = comuna
    db.flush()

    # Grafo: cada barrio se une con sus 3 vecinos mas cercanos y luego se
    # agregan las uniones minimas (Kruskal) para que toda la ciudad quede conectada.
    hoods = db.scalars(select(models.Neighborhood)).all()
    pos = {h.id: (h.latitude, h.longitude) for h in hoods}
    pairs = set()
    for c in db.scalars(select(models.NeighborhoodConnection)):
        pairs.add(frozenset((c.from_neighborhood_id, c.to_neighborhood_id)))

    def connect(a: int, b: int) -> None:
        key = frozenset((a, b))
        if a == b or key in pairs:
            return
        pairs.add(key)
        db.add(
            models.NeighborhoodConnection(
                from_neighborhood_id=a, to_neighborhood_id=b, distance_meters=_distance_m(pos[a], pos[b]), road_name=None
            )
        )

    new_ids = {h.id for h in added}
    for h in added:
        near = sorted((o for o in pos if o != h.id), key=lambda o: _distance_m(pos[h.id], pos[o]))[:3]
        for o in near:
            connect(h.id, o)

    parent = {i: i for i in pos}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for key in pairs:
        a, b = tuple(key)
        parent[find(a)] = find(b)
    if len({find(i) for i in pos}) > 1:
        ids = list(pos)
        edges = sorted(
            (_distance_m(pos[a], pos[b]), a, b) for i, a in enumerate(ids) for b in ids[i + 1 :] if a in new_ids or b in new_ids
        )
        for _, a, b in edges:
            if find(a) != find(b):
                parent[find(a)] = find(b)
                connect(a, b)
    db.commit()
    return len(added)


def ensure_alert_expiration(db: Session) -> None:
    """
    Vencimiento de alertas: cada tipo necesita su duracion y cada alerta
    publicada necesita saber cuando se publico. Solo llena lo que falte.
    """
    changed = False
    for t in db.scalars(select(models.IncidentType).where(models.IncidentType.duration_minutes.is_(None))):
        t.duration_minutes = DEFAULT_DURATIONS.get(t.code, DEFAULT_DURATION)
        changed = True
    pending = db.scalars(
        select(models.Report).where(models.Report.status.in_(("published", "verified")), models.Report.published_at.is_(None))
    ).unique().all()
    for r in pending:
        when = db.scalar(
            select(models.ReportStatusHistory.changed_at)
            .where(models.ReportStatusHistory.report_id == r.id, models.ReportStatusHistory.new_status == "published")
            .order_by(models.ReportStatusHistory.changed_at.desc())
            .limit(1)
        )
        r.published_at = when or r.created_at
        changed = True
    if changed:
        db.commit()


def ensure_extra_incident_types(db: Session) -> int:
    """
    Agrega los tipos del catalogo que falten y llena la categoria de los que no
    la tienen. No duplica un tipo que el admin ya haya creado con el mismo nombre
    ni cambia lo que el admin haya editado. Devuelve cuantos tipos agrego.
    """
    rows = db.scalars(select(models.IncidentType)).all()
    by_code = {t.code: t for t in rows}
    names = {_norm(t.name): t for t in rows}
    for t in rows:
        if not t.category:
            t.category = BASE_CATEGORY.get(t.code, "Otros")
    added = 0
    for code, name, severity, color, minutes, category in EXTRA_INCIDENT_TYPES:
        if code in by_code:
            continue
        same = names.get(_norm(name))
        if same is not None:
            same.category = same.category if same.category and same.category != "Otros" else category
            continue
        db.add(
            models.IncidentType(
                code=code, name=name, severity_level=severity, color=color, duration_minutes=minutes, category=category
            )
        )
        added += 1
    db.commit()
    return added


def ensure_profesor(db: Session) -> None:
    """Crea (o actualiza la clave de) las cuentas del profesor: una administradora y una de vecino normal."""
    settings = get_settings()
    if not settings.profesor_password:
        return
    centro = db.scalar(select(models.Neighborhood).where(models.Neighborhood.name == "Centro"))
    accounts = [
        (settings.profesor_email, "Profesor", "admin"),
        (settings.profesor_user_email, "Profesor (vecino)", "citizen"),
    ]
    password_hash = hash_password(settings.profesor_password)
    for email, full_name, role_name in accounts:
        role = db.scalar(select(models.Role).where(models.Role.name == role_name))
        if role is None or not email:
            continue
        email = email.lower()
        user = db.scalar(select(models.User).where(models.User.email == email))
        if user is None:
            user = models.User(full_name=full_name, email=email, role=role, neighborhood=centro, password_hash=password_hash)
            db.add(user)
            db.flush()
            if role_name == "citizen" and centro is not None:
                # suscrito al Centro para que le lleguen las alertas de su barrio
                db.add(models.Subscription(user_id=user.id, neighborhood_id=centro.id))
        user.password_hash = password_hash
    db.commit()


def init_db(with_seed: bool = True) -> None:
    Base.metadata.create_all(bind=db_engine)
    add_missing_columns()
    db = SessionLocal()
    try:
        if with_seed:
            seed(db)
        migrate_to_pasto(db)
        sync_pasto_barrios(db)
        ensure_alert_expiration(db)
        ensure_extra_incident_types(db)
        ensure_profesor(db)
    finally:
        db.close()


if __name__ == "__main__":
    init_db(True)
    print("Base de datos creada y con datos de ejemplo.")

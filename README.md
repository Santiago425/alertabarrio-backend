# AlertaBarrio · Backend

API REST en **Python + FastAPI** sobre **PostgreSQL**. Aquí viven las estructuras de datos del proyecto (`app/structures/`), implementadas por nosotros y usadas por `AlertEngine` (`app/services/engine.py`).

Ciudad: **San Juan de Pasto** (14 barrios con sus vías para la ruta segura).

- `GET /api/v1/hello` → hola mundo + integrantes
- `GET /api/v1/stats` → números del dashboard
- Swagger: `/docs`

## Estructura

```
app/
  structures/     dynamic_array, linked_list, stack, queue, priority_queue,
                  hash_table, bst (AVL), graph (BFS/DFS/Dijkstra), sorting
  services/       engine.py (todas las estructuras), report_service.py, ai_client.py
  routers/        auth, reports, moderation, notifications, routes, ai, catalog, general
  models.py       14 tablas (SQLAlchemy)
  seed.py         datos de ejemplo
tests/            test_structures.py, test_api.py
```

## Endpoints principales

| Método | Ruta | Estructura |
|---|---|---|
| POST | `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/change-password` | — (bcrypt + JWT) |
| POST | `/api/v1/auth/2fa/setup`, `/api/v1/auth/2fa/enable`, `/api/v1/auth/2fa/disable`, `/api/v1/auth/logout-all` | — (verificación en dos pasos TOTP y cierre de todas las sesiones) |
| POST | `/api/v1/reports` | ciclo completo con IA → PriorityQueue + AVL + Stack |
| GET | `/api/v1/feed?neighborhood_id=` | LinkedList / merge sort |
| GET | `/api/v1/reports?from=&to=` | AVL (rango por fecha) |
| GET | `/api/v1/reports/{id}/history` | Stack |
| POST | `/api/v1/reports/{id}/verify` | — |
| GET | `/api/v1/moderation/queue` | PriorityQueue (heap) |
| POST | `/api/v1/moderation/next` | pop del heap |
| POST | `/api/v1/moderation/reports/{id}/publish` | LinkedList + Queue de notificaciones |
| POST | `/api/v1/moderation/reports/{id}/undo` | pop de la Stack |
| GET | `/api/v1/routes/safe?from_id=&to_id=` | Graph + Dijkstra + BFS |
| GET | `/api/v1/neighborhoods/search?name=` | búsqueda binaria |
| GET | `/api/v1/neighborhoods/ranking` | quick sort |
| GET | `/api/v1/ai/heatmap`, `/api/v1/ai/daily-summary` | llaman al componente de IA |
| POST | `/api/v1/ai/chat` | asistente: pregunta del vecino + datos reales (ranking, horas de riesgo, alertas recientes) → IA (Gemini) |
| POST | `/api/v1/ai/report-draft` | Vigía: el vecino cuenta lo que pasó (voz o texto) y la IA arma el reporte; el barrio sale del GPS |
| POST | `/api/v1/ai/route` | Vigía: "estoy en la U, necesito ir al centro" → Graph + Dijkstra desde la ubicación del vecino |
| GET | `/api/v1/neighborhoods/nearest?lat=&lng=` | barrio al que pertenece un punto del mapa (haversine) |
| GET | `/api/v1/ds/state` | estado interno de todas las estructuras |
| GET/POST/PATCH/DELETE | `/api/v1/admin/incident-types` | **Configuración de alertas** (solo admin): crear tipos, renombrarlos, gravedad, color y duración en el mapa |
| POST | `/api/v1/moderation/reports/{id}/withdraw` | el admin retira del mapa una alerta publicada (queda en el historial) |
| GET | `/api/v1/stats/zones?months=&neighborhood_id=&comuna=&incident_type_id=` | estadísticas por mes, barrio, comuna, hora y día (incluye alertas vencidas) |
| GET/PATCH/DELETE | `/api/v1/routes/history` | historial de rutas seguras del usuario (se guardan solas al consultarlas) |

## Vencimiento de alertas

Cada tipo de alerta tiene una **duración** (`incident_types.duration_minutes`, la configura el admin). Desde que el moderador publica la alerta (`reports.published_at`) empieza a contar; al vencer **sale del mapa, del feed y de la ruta segura**, pero el reporte sigue en la base de datos con su estado, así que cuenta para el historial y las estadísticas. Si el admin cambia la duración, aplica de una a las alertas que ya están publicadas. Duración `0` = no vence.

## Tipos de incidentes

Hay un catálogo de **~50 tipos** organizado por categorías (Seguridad, Tránsito, Emergencias, Servicios públicos, Convivencia y Otros), basado en el Código de Policía (Ley 1801), las categorías de la Policía Nacional y la Línea 123. Cada uno trae su gravedad y su duración en el mapa. Al arrancar, el backend agrega los que falten sin duplicar los que el admin ya creó. Para lo que no esté en la lista existe **"Otro"**, y el admin puede crear tipos nuevos desde Configuración de alertas (salen de una para reportar, en el mapa y en las estadísticas).

## Moderación

1. El vecino reporta → queda **pendiente** (nadie más lo ve).
2. El administrador/moderador lo revisa: **Publicar** (sale en el mapa y avisa a los suscritos) o **Rechazar** (no se publica).
3. Una alerta publicada se puede **Retirar** si era falsa; cualquier decisión se puede **Deshacer** (pila).
4. El usuario normal **no puede borrar ni editar** alertas: solo reportar y confirmar ("Yo también lo vi").

## Seguridad de las contraseñas

- **Nunca se guardan en texto plano.** Se guarda un hash **bcrypt** con costo 12 (2¹² rondas) y sal aleatoria por usuario: dos cuentas con la misma contraseña tienen hashes distintos y el hash no se puede revertir.
- **Contraseña fuerte obligatoria:** mínimo 8 caracteres, mayúscula, minúscula, número y símbolo (`validate_password_strength` en `app/security.py`).
- **Bloqueo por intentos:** 5 intentos fallidos seguidos bloquean ese correo 10 minutos (responde `429`).
- **Sin pistas:** si el correo no existe se hace igual un bcrypt, así la respuesta tarda lo mismo y no se puede saber qué correos están registrados.
- **Rehash automático:** si se sube `BCRYPT_ROUNDS`, el hash de cada usuario se actualiza solo la próxima vez que inicia sesión.
- En producción hay que poner un `JWT_SECRET` largo y secreto (si queda el de ejemplo, el backend lo avisa en el log).

## Cuentas de prueba

Las crea el seed al arrancar con la clave de `DEMO_PASSWORD` (por defecto `Alerta2026*`):

| Correo | Rol |
|---|---|
| `admin@alertabarrio.co` | administrador (entrar con el switch "Administrador") |
| `moderador@alertabarrio.co` | moderador (switch "Administrador") |
| `ana@alertabarrio.co` | vecina (switch "Usuario") |
| `profesor@alertabarrio.co` | administrador, clave en `PROFESOR_PASSWORD` |

## Variables de entorno

Nada sensible queda en el código: todo se lee de variables de entorno (archivo `.env` en local, ver `.env.example`) en `app/config.py`.

## Correr en local

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env        # ajustar DATABASE_URL
uvicorn app.main:app --reload --port 8000
pytest                      # usa SQLite temporal si no hay DATABASE_URL
```

Con Docker: `docker build -t alertabarrio-backend . && docker run -p 8000:8000 --env-file .env alertabarrio-backend`

Diagrama entidad-relación: [`database/er_diagram.png`](database/er_diagram.png).

   Revisado por Neber Melo: despliegue del backend en Render.

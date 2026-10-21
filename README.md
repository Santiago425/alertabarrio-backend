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
| GET | `/api/v1/ds/state` | estado interno de todas las estructuras |

## Seguridad de las contraseñas

- **Nunca se guardan en texto plano.** Se guarda un hash **bcrypt** con costo 12 (2¹² rondas) y sal aleatoria por usuario: dos cuentas con la misma contraseña tienen hashes distintos y el hash no se puede revertir.
- **Contraseña fuerte obligatoria:** mínimo 8 caracteres, mayúscula, minúscula, número y símbolo (`validate_password_strength` en `app/security.py`).
- **Bloqueo por intentos:** 5 intentos fallidos seguidos bloquean ese correo 10 minutos (responde `429`).
- **Sin pistas:** si el correo no existe se hace igual un bcrypt, así la respuesta tarda lo mismo y no se puede saber qué correos están registrados.
- **Rehash automático:** si se sube `BCRYPT_ROUNDS`, el hash de cada usuario se actualiza solo la próxima vez que inicia sesión.
- En producción hay que poner un `JWT_SECRET` largo y secreto (si queda el de ejemplo, el backend lo avisa en el log).

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

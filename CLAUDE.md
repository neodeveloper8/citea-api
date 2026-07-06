# CLAUDE.md — citea-api

> Contexto del proyecto para Claude Code. Leer antes de generar o modificar código.

## Qué es Citea

Marketplace web para descubrir y reservar servicios en negocios de belleza
(salones, barberías, spas, estéticas) en Arequipa, Perú. Este repo es el
backend. El frontend vive en un repo aparte: `citea-web` (React + Vite).

Alternativa local a Fresha. Competimos en descubrimiento, reserva y relación
cliente-negocio, NO en gestión interna del salón (caja, inventario, planilla).

## Stack

- Python 3.11+ / Django 6.x + Django REST Framework
- PostgreSQL (Supabase remoto, vía Session pooler, puerto 5432)
- Auth: JWT (djangorestframework-simplejwt) con blacklist de refresh token
- Config sensible: leída del `.env` con python-decouple + dj-database-url

## Estructura de apps (por dominio, no por tipo de archivo)

- `core`     → transversal: TimeStampedModel (abstracto), exceptions, permisos base, utils. Sin modelos de negocio.
- `users`    → custom User model, auth, roles. (IMPLEMENTADO, Fase 1.)
- `businesses` → Category, Business, BusinessHours, Service, BusinessImage. (IMPLEMENTADO, Fase 2.)
- `bookings` → Booking, Review, ReviewResponse. (Review vive acá: no existe sin un Booking.) (IMPLEMENTADO, Fase 2.)

## Modelos existentes (Fase 2 — todos migrados y aplicados)

Todos heredan de core.TimeStampedModel (created_at, updated_at).

businesses:
- Category(name, slug auto, is_active, order)
- Business(owner FK→User CASCADE, category FK→Category PROTECT, name, slug auto+único,
  description, address, phone, whatsapp, email, latitude/longitude Decimal nullable,
  status [draft/pending/approved/rejected/suspended], rejection_reason)
- BusinessHours(business FK CASCADE, weekday [0=Lunes], open_time, close_time) — varias filas/día
- Service(business FK CASCADE, name, description, duration_minutes int, price Decimal 8,2, is_active)
- BusinessImage(business FK CASCADE, public_id, image_url, alt_text, is_cover, order) — 1 portada/negocio

bookings:
- Booking(customer FK→User CASCADE, business FK CASCADE, service FK PROTECT, start_datetime,
  end_datetime, price_at_booking, duration_at_booking, status, source, is_first_booking_for_business,
  customer_note) — price y duration son SNAPSHOT congelado al crear
- Review(booking OneToOne CASCADE, rating 1-5, comment) — solo si booking COMPLETED
- ReviewResponse(review OneToOne CASCADE, body)

Cloudinary: SDK directo (paquete cloudinary), configurado en base.py. BusinessImage guarda
public_id + image_url como campos planos. El uploader real (cloudinary.uploader.upload) se
implementa en Fase 3. NO se usa django-cloudinary-storage ni CloudinaryField.

## Roles del sistema (campo `role` en User)

- `cliente`        → usuario final que reserva.
- `dueno`          → dueño de un negocio que recibe reservas.
- `platform_admin` → operador de Citea. NO confundir con superuser técnico.

## Convenciones

- Naming Python: snake_case (variables/funciones), PascalCase (clases/modelos).
- Endpoints: kebab-case y en plural → `/businesses/`, `/password-reset/`.
- Serializers: uno por acción cuando convenga (ListSerializer, DetailSerializer, CreateSerializer).
- Permisos: custom permission classes de DRF, NO decoradores.
- Choices: usar TextChoices, nunca strings sueltos repartidos por el código.

## Formato de respuestas API

- ÉXITO: formato nativo de DRF (objeto, lista, o paginación con count/next/previous/results). NO envolver en wrapper.
- ERROR: shape PLANO uniforme, vía core.exceptions.custom_exception_handler:
```json
  {
    "error": "Mensaje legible para el usuario.",
    "code": "validation_error",
    "details": { "campo": ["..."] }
  }
```
  NOTA: `error` es el string del mensaje; `code` y `details` son hermanos al nivel raíz
  (NO anidados dentro de `error`). Este formato está implementado y cubierto por tests.

## Reglas que NO se rompen

- NUNCA hardcodear secrets, tokens, passwords ni API keys. Todo vía `.env`.
- NUNCA commitear el archivo `.env`.
- SIEMPRE validar inputs en el backend (no confiar en el frontend).
- SIEMPRE password hashing nativo de Django (jamás SHA-256 plano).
- Migraciones: revisar antes de aplicar. Nunca editar a mano una migración ya aplicada.

## Modelo de negocio (afecta decisiones de datos)

- Monetización: suscripción mensual por tiers al dueño del negocio. NO comisión por reserva.
- `Booking.source` (`marketplace` | `direct`): se guarda como MÉTRICA (cuántas reservas
  generó el marketplace), NO como base de cobro. Sirve para demostrar valor al dueño.
- La lógica de comisiones / first booking NO existe: el modelo es suscripción, no comisión.
- Monetización confirmada (2026-06-11): suscripción mensual por tiers al dueño. Alineado con PROYECTO.md.

## Cómo trabajar en este repo

- Avanzamos por fases. No adelantarse a fases futuras.
- Cuando se pida una tarea acotada, hacer SOLO eso y frenar. No agregar campos,
  endpoints ni lógica "de más" sin pedirlo.
- NO asumir el estado del código: ante la duda, inspeccionar el repo real antes de proponer.

## Decisiones técnicas fijas (no cambiar sin discutir)

- User hereda de AbstractBaseUser + PermissionsMixin. Login por email. NO usar AbstractUser, NO hay username.
- Config vía python-decouple + dj-database-url. NO usar django-environ.
- Settings divididos: config/settings/{base,local,production,test}.py. Default local.
- test.py usa SQLite en memoria + MD5PasswordHasher + sin throttling (tests rápidos y aislados).
- Driver Postgres: psycopg2-binary. Venv oficial: venv/ (NO .venv/).
- Permisos: custom permission classes, no decoradores. Ya existen: IsCliente, IsDueno, IsPlatformAdmin, IsOwnerOrReadOnly.
- IsOwnerOrReadOnly usa owner_field configurable por la view (default "owner"). Recorre la
  ruta al dueño (ej: la view de Service declara owner_field = "business.owner"). YA ajustado.
- Errores: formato JSON PLANO { "error", "code", "details" } vía core.exceptions.custom_exception_handler.
- Logout invalida el refresh token vía token_blacklist. El access expira solo (30 min).
- Reset/verify usan default_token_generator (un solo uso), NO JWT.
- Tests: pytest + pytest-django. Correr con `pytest` (usa config.settings.test).
- Django 6.x: varias APIs cambiaron vs 4/5. Ej: CheckConstraint usa condition=, no check=.
  Verificar compatibilidad de libs de terceros antes de instalar.
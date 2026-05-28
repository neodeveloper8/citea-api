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
- PostgreSQL (Supabase remoto, vía Session pooler)
- Auth: JWT (djangorestframework-simplejwt) — se agrega en Fase 1
- Config sensible: leída del `.env` con python-decouple + dj-database-url

## Estructura de apps (por dominio, no por tipo de archivo)

- `core`     → transversal: formato de respuestas/errores, paginación, permisos base, utils. Sin modelos de negocio.
- `users`    → custom User model, auth, roles.
- `businesses` → Business, Category, BusinessHours, Service, BusinessImage, verificación.
- `bookings` → Booking, Review, ReviewResponse. (Review vive acá: no existe sin un Booking.)

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
- ERROR: shape custom uniforme, vía un custom exception handler en `core`:
```json
  {
    "error": {
      "code": "validation_error",
      "message": "Mensaje legible para el usuario.",
      "details": { "campo": ["..."] }
    }
  }
```

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
- La lógica de comisiones / first booking queda fuera del MVP.

## Cómo trabajar en este repo

- Avanzamos por fases. No adelantarse a fases futuras.
- Cuando se pida una tarea acotada, hacer SOLO eso y frenar. No agregar campos,
  endpoints ni lógica "de más" sin pedirlo.
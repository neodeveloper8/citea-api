# citea-api

Backend del marketplace de reservas de belleza [Citea](https://github.com/gonzaloast/citea-web) — descubrí y reservá servicios en salones, barberías y spas en Arequipa, Perú. El frontend vive en el repo `citea-web`.

## Stack

- Python 3.11+ · Django 6.x · Django REST Framework
- PostgreSQL (Supabase, vía Session pooler)
- Configuración sensible vía `python-decouple` + `dj-database-url`

## Setup local

1. Clonar el repo:
   ```bash
   git clone https://github.com/gonzaloast/citea-api.git
   cd citea-api
   ```

2. Crear y activar el entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Copiar el archivo de variables de entorno y completarlo:
   ```bash
   cp .env.example .env
   ```

5. Aplicar migraciones:
   ```bash
   python manage.py migrate
   ```

6. Crear superusuario:
   ```bash
   python manage.py createsuperuser
   ```

7. Levantar el servidor:
   ```bash
   python manage.py runserver
   ```

## Variables de entorno

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave secreta de Django. Generá una con `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `True` en desarrollo, `False` en producción. |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por coma. Ej: `127.0.0.1,localhost` |
| `DATABASE_URL` | URL de conexión a PostgreSQL. Ej: `postgres://user:pass@host:5432/db` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para CORS, separados por coma. Ej: `http://localhost:5173` |

## Estructura del proyecto

| App | Responsabilidad |
|---|---|
| `core` | Transversal: formato de respuestas/errores, paginación, permisos base y utils. Sin modelos de negocio. |
| `users` | Custom User model, autenticación y roles (`cliente`, `dueno`, `platform_admin`). |
| `businesses` | Negocios, categorías, horarios, servicios e imágenes. |
| `bookings` | Reservas, reseñas y respuestas a reseñas. |

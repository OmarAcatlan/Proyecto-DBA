# Guía de Inicio Rápido del Entorno de Desarrollo

Este documento explica cómo levantar y gestionar el entorno de desarrollo Docker para el proyecto de base de datos de empleados.

## Requisitos Previos

- **Docker Desktop:** Asegúrate de que Docker Desktop esté instalado y en ejecución en tu sistema.

## Cómo Iniciar el Entorno

Hemos creado un script de automatización para facilitar el proceso de inicio y configuración. Este script se encargará de todo, desde la configuración inicial hasta la inicialización de las bases de datos y la instalación de dependencias.

**Para iniciar todo el entorno, ejecuta el siguiente comando desde el directorio `development`:**

```bash
bash setup_and_start.sh
```

### ¿Qué hace el script `setup_and_start.sh`?

1.  **Crea un archivo `.env`:** Si no existe, crea un archivo `.env` con las variables de entorno necesarias para los servicios de Docker (credenciales de la base de datos, tokens, etc.).
2.  **Ejecuta `start.sh`:** Levanta todos los contenedores Docker en modo detached, incluyendo PostgreSQL, Airflow, Jupyter, Grafana y Prometheus.
3.  **Espera a PostgreSQL:** El script espera 2 minutos para dar tiempo a que la base de datos `employees` se cargue por completo. **Este es el paso que más tiempo consume.**
4.  **Configura la Base de Datos de Airflow:** Crea el usuario y la base de datos para Airflow en PostgreSQL y ejecuta las migraciones necesarias.
5.  **Instala Dependencias de Jupyter:** Instala la librería `psycopg2-binary` en el contenedor de Jupyter para permitir la conexión a la base de datos PostgreSQL desde los notebooks.
6.  **Muestra un Mensaje de Éxito:** Al final, te mostrará las URLs para acceder a los diferentes servicios.

## Acceso a los Servicios

Una vez que el script `setup_and_start.sh` haya terminado, podrás acceder a los servicios en las siguientes URLs:

-   **Grafana:** [http://localhost:3000](http://localhost:3000)
-   **Airflow:** [http://localhost:8080](http://localhost:8080)
    -   **Usuario:** `airflow`
    -   **Contraseña:** `airflow`
-   **Jupyter:** [http://localhost:8888](http://localhost:8888)
    -   **Token:** `a_very_secret_token` (si te lo pide)

## Cómo Probar la Conexión a la Base de Datos

1.  Abre Jupyter en [http://localhost:8888](http://localhost:8888).
2.  Crea un nuevo notebook.
3.  Pega y ejecuta el siguiente código en una celda:

```python
import psycopg2

# Detalles de conexión
db_host = "postgres"
db_name = "employees"
db_user = "admin"
db_password = "admin"
db_port = "5432"

try:
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
        user=db_user,
        password=db_password,
        port=db_port
    )
    cur = conn.cursor()
    query = "SELECT emp_no, first_name, last_name FROM employees LIMIT 5;"
    cur.execute(query)
    rows = cur.fetchall()
    print("Conexión exitosa y consulta ejecutada:")
    for row in rows:
        print(row)
except Exception as e:
    print(f"Error al conectar o ejecutar la consulta: {e}")
finally:
    if cur:
        cur.close()
    if conn:
        conn.close()
    print("Conexión cerrada.")
```

Este código debería conectarse a la base de datos `employees` y mostrar los primeros 5 empleados.

## Cómo Detener el Entorno

Para detener todos los servicios, puedes ejecutar el siguiente comando desde el directorio `development`:

```bash
docker compose down
```

Si deseas detener los servicios y **eliminar todos los datos** (incluyendo las bases de datos), usa:

```bash
docker compose down -v
```

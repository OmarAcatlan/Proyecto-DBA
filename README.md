# Resumen del Proyecto de Análisis de Datos

Este documento describe la arquitectura, tecnologías y metodologías del proyecto actual, y sirve como base para la implementación de un nuevo sistema utilizando un script de Bash para la automatización y la base de datos `employees` para pruebas de rendimiento.

## 1. Descripción General del Proyecto

El proyecto consiste en una plataforma de análisis de datos contenerizada que integra varias herramientas de código abierto. La plataforma ingiere datos, los procesa y permite su análisis y visualización. La orquestación de los servicios se realiza con Docker Compose.

## 2. Tecnologías Principales

- **Contenerización:** Docker, Docker Compose
- **Base de Datos:** PostgreSQL 10
- **Orquestación de Flujos de Trabajo (ETL):** Apache Airflow 2.9.1
- **Análisis de Datos y Notebooks:** Jupyter Notebook, Pandas, Matplotlib, Sympy
- **Monitoreo:** Prometheus
- **Visualización de Métricas:** Grafana
- **Automatización (Propuesta):** Script de Bash

## 3. Arquitectura y Metodología

El sistema sigue una arquitectura de microservicios, donde cada componente se ejecuta en su propio contenedor Docker:

1.  **Base de Datos (`postgres`):** Almacenará la base de datos `employees` para el análisis y la metadata de Airflow.
2.  **Carga de Datos (Nuevo Plan):** Al iniciar, el contenedor de `postgres` ejecutará automáticamente los scripts `.sql` del repositorio `test_db` para crear el esquema y poblar la base de datos `employees`.
3.  **Orquestación (`airflow-*`):** Permitirá definir, programar y monitorear flujos de trabajo (DAGs) para el procesamiento y análisis de los datos de `employees`.
4.  **Entorno de Análisis (`pyspark`):** Proporcionará un entorno interactivo con Jupyter y PySpark para analizar el gran volumen de datos.
5.  **Monitoreo y Visualización (`prometheus`, `grafana`):** Capturarán y mostrarán métricas de rendimiento de la base de datos y los servicios.

## 4. Propuesta de Nueva Implementación

### Automatización con Bash

Un script de Bash (ej. `start.sh`) orquestará el ciclo de vida del entorno, reemplazando la lógica actual de Terraform.

El script `setup_and_start.sh` se encargará de:
1.  Clonar el repositorio `test_db` si no existe.
2.  Cargar variables de entorno, ** siempre y cuando no exista ya un archivo .env, hay un archivo env-example que servira de guia** .
3.  Ejecutar los comandos de `docker-compose` para construir y levantar los servicios.

```bash
#!/bin/bash

# Cargar variables de entorno
export $(cat .env | xargs)

# Clonar el repositorio de datos si no existe
if [ ! -d "test_db" ]; then
  git clone https://github.com/datacharmer/test_db.git
fi

# Preparar los scripts de inicialización de la BD
# (Aquí iría la lógica para copiar/adaptar los .sql)

# Detener y limpiar entorno
docker compose down -v

# Construir imágenes
docker compose build

# Levantar servicios
docker compose up -d
```
## 5.Variables de entorno - Configuración del proyecto

### 1. Configuración de PostgreSQL

Variable: POSTGRES_HOST
Valor por defecto: postgres
Descripción: Hostname del servidor PostgreSQL. Usa el mismo nombre que el servicio en docker-compose para facilitar la conexión

Variable: POSTGRES_PORT
Valor por defecto: 5432
Descripción: Puerto estándar de PostgreSQL

Variable: POSTGRES_USER
Valor por defecto: admin
Descripción: Usuario administrador de PostgreSQL

Variable: POSTGRES_PASSWORD
Valor por defecto: admin
Descripción: Contraseña del usuario administrador

Variable: POSTGRES_DB
Valor por defecto: employees
Descripción: Base de datos principal para operaciones del sistema

### 2. Configuración de Airflow

Variable: AIRFLOW_USER
Valor por defecto: airflow
Descripción: Usuario principal de Airflow

Variable: AIRFLOW_PASSWORD
Valor por defecto: airflow
Descripción: Contraseña del usuario de Airflow

Variable: POSTGRES_DB_AIRFLOW
Valor por defecto: airflow
Descripción: Base de datos exclusiva para Airflow (metadatos)

Variable: AIRFLOW_WEBSERVER_SECRET_KEY
Valor por defecto: a_very_secret_key
Descripción: Clave secreta para el servidor web de Airflow

Variable: AIRFLOW_CONN_ID
Valor por defecto: postgresadb
Descripción: ID de conexión PostgreSQL que se creará automáticamente

### 3. Configuración de Jupyter Notebook

Variable: JUPYTER_TOKEN
Valor por defecto: a_very_secret_token
Descripción: Token de autenticación para Jupyter Notebook

Variable: PATH_LOCAL_USER
Valor por defecto: ./jupyter_notebook
Descripción: Ruta local para almacenar notebooks de Jupyter

### 4. Configuración para DAGs de Validación de Datos (hr-data-validation)

### Servicio de correo electrónico

Variable: SMTP_SERVER
Ejemplo: smtp.gmail.com
Descripción: Servidor SMTP para envío de correos (específico para Gmail)

Variable: SMTP_PORT
Ejemplo: 587
Descripción: Puerto SMTP para envío de correos (específico para Gmail)

Variable: SENDER_EMAIL
Ejemplo: tu_correo@gmail.com
Descripción: Dirección de correo remitente

Variable: SENDER_PASSWORD
Ejemplo: TuContraseñaApp
Descripción: Contraseña de aplicación generada siguiendo este tutorial: https://www.youtube.com/watch?v=ZfEK3WP73eY. Importante: eliminar espacios

Variable: RECEIVER_EMAILS
Ejemplo: email1@gmail.com,email2@dominio.com
Descripción: Lista de destinatarios separados por comas

---

### Archivo .env de ejemplo:

#### PostgreSQL Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
POSTGRES_DB=employees

#### Airflow Configuration
AIRFLOW_USER=airflow
AIRFLOW_PASSWORD=airflow
POSTGRES_DB_AIRFLOW=airflow
AIRFLOW_WEBSERVER_SECRET_KEY=a_very_secret_key
AIRFLOW_CONN_ID=postgresadb

#### Jupyter Configuration
JUPYTER_TOKEN=a_very_secret_token
PATH_LOCAL_USER=./jupyter_notebook

#### Email Configuration for DAGs
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=tu_correo@gmail.com
SENDER_PASSWORD=TuContraseñaAppGenerada
RECEIVER_EMAILS=destinatario1@gmail.com,destinatario2@empresa.com
#### Notas importantes:
1. El archivo .env debe ubicarse al mismo nivel que el .gitignore, *Hay un env-example*
2. Para SENDER_PASSWORD: usar contraseñas de aplicación de Google, no la contraseña personal
3. Las variables marcadas como específicas para Gmail pueden requerir ajustes si usas otro proveedor



# Fuente de Datos: `employees`

- **Repositorio:** `https://github.com/datacharmer/test_db`
- **Plan de Integración:**
    1.  Los scripts `.sql` del repositorio `test_db` se montarán en el directorio `/docker-entrypoint-initdb.d` del contenedor `postgres`.
    2.  El contenedor, en su primer arranque, ejecutará estos scripts para crear la estructura y cargar los datos de la base de datos `employees`.
    3.  Se eliminará el servicio `pgloader`, ya que no será necesario.
    4.  **Posible Desafío:** Será necesario revisar y posiblemente adaptar la sintaxis de los archivos `.sql` de MySQL a PostgreSQL.

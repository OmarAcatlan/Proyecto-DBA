#!/bin/bash

# Salir si ocurre un error
set -e

# --- 1. Configuración del Entorno ---
echo "--- Iniciando la configuración del entorno ---"

# Crear archivo .env si no existe
if [ ! -f ".env" ]; then
  echo "Creando archivo .env con valores por defecto..."
  cat > .env <<EOL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
POSTGRES_DB=employees
AIRFLOW_USER=airflow
AIRFLOW_PASSWORD=airflow
POSTGRES_DB_AIRFLOW=airflow
AIRFLOW_WEBSERVER_SECRET_KEY=a_very_secret_key
JUPYTER_TOKEN=a_very_secret_token
PATH_LOCAL_USER=./jupyter_notebook
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
AIRFLOW_CONN_ID=postgresadb
EOL
else
  echo "Cargando variables de entorno desde .env..."
  set -a && source .env && set +a
fi

# --- 2. Iniciar servicios Docker ---
echo "--- Levantando todos los servicios de Docker con start.sh ---"
bash start.sh

# --- 3. Esperar a que PostgreSQL se inicialice ---
echo "--- Esperando a que PostgreSQL cargue la base de datos 'employees' ---"
echo "Este proceso puede tardar varios minutos. Por favor, ten paciencia."
# Una forma robusta de esperar es verificar si el contenedor está listo para aceptar conexiones
# y si la base de datos 'employees' existe.
sleep 120 # Espera de 2 minutos para la carga inicial de datos.

# --- 4. Corregir y Inicializar la Base de Datos de Airflow ---
echo "--- Configurando la base de datos de Airflow ---"
# Crear el usuario y la base de datos para Airflow en PostgreSQL
docker exec development-postgres-1 psql -U admin -d employees -c "CREATE USER airflow WITH PASSWORD 'airflow';"
docker exec development-postgres-1 psql -U admin -d employees -c "CREATE DATABASE airflow OWNER airflow;"
docker exec development-postgres-1 psql -U admin -d employees -c "GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;"

# Forzar la reinicialización de la base de datos de Airflow
echo "--- Inicializando la base de datos de Airflow ---"
docker compose up --force-recreate --no-deps -d airflow-init
sleep 30 # Dar tiempo a que airflow-init termine

# Reiniciar los servicios de Airflow para que se conecten a la BD inicializada
echo "--- Reiniciando los servicios de Airflow ---"
docker restart development-airflow-webserver-1 development-airflow-scheduler-1

# --- 5. Instalar dependencias en Jupyter ---
echo "--- Instalando 'psycopg2-binary' en el contenedor de Jupyter ---"
docker exec development-pyspark-1 pip install psycopg2-binary

# --- 6. Finalización ---
echo "--- ¡El entorno se ha configurado y iniciado correctamente! ---"
echo ""
echo "Puedes acceder a los servicios en las siguientes URLs:"
echo "Grafana: http://localhost:3000"
echo "Airflow: http://localhost:8080 (user: airflow, pass: airflow)"
echo "Jupyter: http://localhost:8888 (token: a_very_secret_token)"

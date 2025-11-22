#!/bin/bash

# Salir si ocurre un error
set -e

# Cargar variables de entorno si el archivo .env existe
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Generar el archivo init.sql
echo "Generando el archivo de inicialización de la base de datos (init.sql)..."

cat \
    ./init-db/load_departments.dump \
    ./init-db/load_employees.dump \
    ./init-db/load_dept_emp.dump \
    ./init-db/load_dept_manager.dump \
    ./init-db/load_titles.dump \
    ./init-db/load_salaries1.dump \
    ./init-db/load_salaries2.dump \
    ./init-db/load_salaries3.dump > ./init-db/init.sql

echo "Deteniendo y limpiando el entorno anterior..."
docker compose down -v --remove-orphans

echo "Construyendo imágenes..."
docker compose build

echo "Levantando servicios en modo detached..."
docker compose up -d

echo "El entorno se ha iniciado correctamente."
echo "La base de datos 'employees' se está cargando. Esto puede tardar varios minutos."
echo "Puedes ver el progreso con: docker logs -f <postgres_container_name>"
echo "---"
echo "Grafana: http://localhost:3000"
echo "Airflow: http://localhost:8080"
echo "Jupyter: http://localhost:8888"

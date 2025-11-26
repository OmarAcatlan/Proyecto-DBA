#!/bin/bash
echo "Deteniendo y eliminando contenedores..."
docker-compose down
docker rm -f $(docker ps -aq) 2>/dev/null

echo "Eliminando volúmenes..."
docker volume rm $(docker volume ls -q) 2>/dev/null
docker volume prune -f

echo "Eliminando networks..."
docker network prune -f

echo "Eliminando imágenes de Airflow..."
docker rmi apache/airflow:2.9.1 2>/dev/null

echo "Limpieza de directorios del proyecto..."
rm -rf ./airflow/logs/ ./airflow/plugins/

echo "Limpieza completada!"
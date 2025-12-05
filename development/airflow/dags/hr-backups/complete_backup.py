from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta
import os

# Corregir obtención de variables de entorno
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'admin')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'employees')
POSTGRES_CONTAINER_ID = os.environ.get('POSTGRES_CONTAINER_ID', 'development-postgres-1')
POSTGRES_BACKUP_PATH = '/var/lib/postgresql/backups/completo/'
POSTGRES_BACKUP_FILE = f'{POSTGRES_DB}_db.dump'
POSTGRES_BACKUP_ROUTE = os.path.join(POSTGRES_BACKUP_PATH, POSTGRES_BACKUP_FILE)

# Configuración del DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='backup_completo',
    default_args=default_args,
    description='DAG para ejecutar pg_dump desde Airflow en contenedor Postgres',
    schedule_interval=None,
    start_date=datetime(2025, 11, 4),
    catchup=False,
    tags=['backup', 'postgres', 'maintenance'],
) as dag:
    
    # Comando mejorado para crear el backup
    dump_command = f"""
    # Crear directorio si no existe y dar permisos
    docker exec {POSTGRES_CONTAINER_ID} bash -c "mkdir -p {POSTGRES_BACKUP_PATH} && chmod 755 {POSTGRES_BACKUP_PATH}"
    
    # Ejecutar pg_dump con mejores opciones
    docker exec {POSTGRES_CONTAINER_ID} pg_dump \
        -U {POSTGRES_USER} \
        -d {POSTGRES_DB} \
        -F c \
        -v \
        -f {POSTGRES_BACKUP_ROUTE}
    
    # Verificar que el backup se creó correctamente
    docker exec {POSTGRES_CONTAINER_ID} bash -c "test -f {POSTGRES_BACKUP_ROUTE} && echo 'Backup creado exitosamente' || echo 'Error: Backup no creado'"
    """
    
    backup_task = BashOperator(
        task_id='backup_postgres',
        bash_command=dump_command,
        # Añadir variables de entorno al operador si es necesario
        env={
            'PGPASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        },
    )

    backup_task
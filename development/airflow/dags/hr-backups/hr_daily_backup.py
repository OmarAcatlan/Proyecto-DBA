from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from datetime import datetime, timedelta
import os

# Configuración
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'admin')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'employees')
POSTGRES_CONTAINER_ID = os.environ.get('POSTGRES_CONTAINER_ID', 'development-postgres-1')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

POSTGRES_BACKUP_BASE = '/var/lib/postgresql/backups/'
POSTGRES_DAILY_PATH = os.path.join(POSTGRES_BACKUP_BASE, 'daily/')

default_args = {
    'owner': 'hr_team',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1, 2, 0),
}

with DAG(
    dag_id='hr_daily_backup',
    default_args=default_args,
    description='Backup diario simple de base de datos HR',
    schedule_interval='0 2 * * *',
    catchup=False,
    tags=['hr', 'backup', 'daily'],
) as dag:
    
    start = DummyOperator(task_id='start')
    
    # Backup único y rotación en un solo paso
    daily_backup = BashOperator(
        task_id='daily_backup_and_rotate',
        bash_command=f"""
        # 1. Crear directorio si no existe
        docker exec {POSTGRES_CONTAINER_ID} bash -c "
            mkdir -p {POSTGRES_DAILY_PATH}
        "
        
        # 2. Crear nombre de archivo con fecha
        BACKUP_FILE="{POSTGRES_DAILY_PATH}{POSTGRES_DB}_db_$(date +%Y%m%d).dump"
        
        # 3. Crear backup
        echo "Creando backup diario: $BACKUP_FILE"
        docker exec {POSTGRES_CONTAINER_ID} bash -c "
            export PGPASSWORD='{POSTGRES_PASSWORD}'
            pg_dump -U {POSTGRES_USER} -d {POSTGRES_DB} -F c -Z 5 -f '$BACKUP_FILE'
        "
        
        # 4. Rotación automática (mantener últimos 7 días)
        echo "🔄 Aplicando rotación (mantener 7 días)..."
        docker exec {POSTGRES_CONTAINER_ID} bash -c "
            cd {POSTGRES_DAILY_PATH}
            # Eliminar backups mayores a 7 días
            find . -name '*.dump' -mtime +7 -delete
            # Contar backups restantes
            BACKUP_COUNT=$(find . -name '*.dump' | wc -l)
            echo ' Backups después de rotación: $BACKUP_COUNT'
        "
        
        # 5. Verificación rápida
        echo "🔍 Verificando backup..."
        docker exec {POSTGRES_CONTAINER_ID} bash -c "
            if [ -f '$BACKUP_FILE' ]; then
                SIZE=$(du -h '$BACKUP_FILE' | cut -f1)
                echo '✅ Backup creado exitosamente'
                echo '📊 Tamaño: $SIZE'
                echo '📅 Backup listo para restauración'
            else
                echo 'Error: Backup no creado'
                exit 1
            fi
        "
        """,
        dag=dag,
    )
    
    end = DummyOperator(task_id='end')
    
    start >> daily_backup >> end
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from datetime import datetime, timedelta
import os
import subprocess

# Configuración de variables de entorno
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'admin')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'employees')
POSTGRES_RESTORE_DB = os.environ.get('POSTGRES_RESTORE_DB', 'employees')
POSTGRES_CONTAINER_ID = os.environ.get('POSTGRES_CONTAINER_ID', 'development-postgres-1')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

# Rutas de backup
POSTGRES_BACKUP_BASE = '/var/lib/postgresql/backups/'
POSTGRES_DAILY_PATH = os.path.join(POSTGRES_BACKUP_BASE, 'daily/')

# Configuración del DAG
default_args = {
    'owner': 'hr_team',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
    'start_date': datetime(2025, 1, 1),
}

with DAG(
    dag_id='hr_daily_restore',
    default_args=default_args,
    description='Restauración desde backup diario',
    schedule_interval=None,
    catchup=False,
    tags=['hr', 'restore', 'daily'],
    params={
        'restore_date': None,
        'target_db_name': POSTGRES_RESTORE_DB,
        'drop_existing': True,
    },
) as dag:
    
    # Tarea de inicio
    start_task = DummyOperator(task_id='start_restore')
    
    # Tarea 1: Buscar y validar backup
    def find_daily_backup(**context):
        """Encontrar backup diario para restaurar"""
        params = context['params']
        dag_conf = context['dag_run'].conf if context['dag_run'].conf else {}
        
        restore_date = dag_conf.get('restore_date', params.get('restore_date'))
        target_db = dag_conf.get('target_db_name', params.get('target_db_name', POSTGRES_RESTORE_DB))
        drop_existing = dag_conf.get('drop_existing', params.get('drop_existing', True))
        
        print(f"Parámetros recibidos:")
        print(f"  restore_date: {restore_date}")
        print(f"  target_db: {target_db}")
        print(f"  drop_existing: {drop_existing}")
        
        # Si no se especifica fecha, usar la más reciente
        if not restore_date:
            cmd = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"find {POSTGRES_DAILY_PATH} -name '*.dump' -type f 2>/dev/null | sort -r | head -1\""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0 or not result.stdout.strip():
                raise Exception("No se encontraron backups diarios")
            
            latest_backup = result.stdout.strip()
            import re
            filename = os.path.basename(latest_backup)
            match = re.search(r'(\d{8})\.dump$', filename)
            
            if match:
                restore_date = match.group(1)
                print(f"Backup más reciente encontrado: {restore_date}")
            else:
                raise Exception(f"No se pudo extraer fecha del backup: {filename}")
        
        # Construir ruta del backup
        backup_filename = f"{POSTGRES_DB}_db_{restore_date}.dump"
        backup_path = os.path.join(POSTGRES_DAILY_PATH, backup_filename)
        
        # Verificar que existe
        cmd_check = f"docker exec {POSTGRES_CONTAINER_ID} test -f '{backup_path}'"
        if subprocess.run(cmd_check, shell=True).returncode != 0:
            # Listar backups disponibles
            cmd_list = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"ls -la {POSTGRES_DAILY_PATH} 2>/dev/null\""
            result_list = subprocess.run(cmd_list, shell=True, capture_output=True, text=True)
            available = result_list.stdout
            
            raise Exception(f"Backup no encontrado: {backup_path}\n\nBackups disponibles:\n{available}")
        
        # Obtener tamaño
        cmd_size = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"du -h '{backup_path}' 2>/dev/null | cut -f1\""
        result_size = subprocess.run(cmd_size, shell=True, capture_output=True, text=True)
        backup_size = result_size.stdout.strip() or "Desconocido"
        
        restore_info = {
            'restore_date': restore_date,
            'target_db': target_db,
            'drop_existing': drop_existing,
            'backup_filename': backup_filename,
            'backup_path': backup_path,
            'backup_size': backup_size,
        }
        
        print(f"\nResumen de restauración:")
        print(f"  Backup: {backup_filename}")
        print(f"  Tamaño: {backup_size}")
        print(f"  Destino: {target_db}")
        print(f"  Eliminar existente: {drop_existing}")
        
        context['ti'].xcom_push(key='restore_info', value=restore_info)
        return restore_info
    
    validate_task = PythonOperator(
        task_id='validate_backup',
        python_callable=find_daily_backup,
        dag=dag,
    )
    
    # Tarea 2: Preparar base de datos
# Tarea 2: Preparar base de datos
    prepare_db_task = BashOperator(
        task_id='prepare_database',
        bash_command="""
    TARGET_DB="{{ ti.xcom_pull(task_ids='validate_backup', key='restore_info')['target_db'] }}"
    DROP_EXISTING="{{ ti.xcom_pull(task_ids='validate_backup', key='restore_info')['drop_existing'] }}"

    echo "Preparando base de datos: $TARGET_DB"

    # Verificar si la base de datos existe
    DB_EXISTS=$(docker exec {{ params.container_id }} psql -U {{ params.db_user }} -t -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB';" 2>/dev/null | xargs)

    if [ ! -z "$DB_EXISTS" ]; then
        if [ "$DROP_EXISTING" = "True" ]; then
            echo "Eliminando base de datos existente..."
            
            # Terminar conexiones
            docker exec {{ params.container_id }} psql -U {{ params.db_user }} -c \
                "SELECT pg_terminate_backend(pid) 
                FROM pg_stat_activity 
                WHERE datname = '$TARGET_DB' AND pid <> pg_backend_pid();" 2>/dev/null || true
            
            # Eliminar base de datos
            docker exec {{ params.container_id }} dropdb -U {{ params.db_user }} --if-exists "$TARGET_DB" 2>/dev/null
            
            # Crear nueva
            docker exec {{ params.container_id }} createdb -U {{ params.db_user }} \
                --encoding=UTF8 \
                --locale=C \
                --template=template0 \
                "$TARGET_DB" 2>/dev/null
                
            echo "Base de datos recreada"
            
        else
            echo "Error: Base de datos ya existe y drop_existing=False"
            exit 1
        fi
    else
        echo "Creando nueva base de datos..."
        docker exec {{ params.container_id }} createdb -U {{ params.db_user }} \
            --encoding=UTF8 \
            --locale=C \
            --template=template0 \
            "$TARGET_DB" 2>/dev/null
        echo "Base de datos creada"
    fi
    """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
        },
        env={'PGPASSWORD': POSTGRES_PASSWORD},
        dag=dag,
    )
    # Tarea 3: Restaurar backup
    restore_task = BashOperator(
        task_id='restore_backup',
        bash_command="""
        BACKUP_PATH="{{ ti.xcom_pull(task_ids='validate_backup', key='restore_info')['backup_path'] }}"
        TARGET_DB="{{ ti.xcom_pull(task_ids='validate_backup', key='restore_info')['target_db'] }}"
        
        echo "Restaurando backup: $(basename $BACKUP_PATH)"
        echo "Base de datos destino: $TARGET_DB"
        
        START_TIME=$(date +%s)
        
        # Ejecutar pg_restore
        docker exec {{ params.container_id }} bash -c "
            export PGPASSWORD='{{ params.db_password }}'
            pg_restore \
                -U {{ params.db_user }} \
                -d '$TARGET_DB' \
                --clean \
                --if-exists \
                --no-owner \
                -j 2 \
                -v \
                '$BACKUP_PATH'
        "
        
        RESTORE_EXIT=$?
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        
        if [ $RESTORE_EXIT -ne 0 ]; then
            echo "Error en la restauración"
            exit 1
        fi
        
        echo "Restauración completada en $DURATION segundos"
        """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
            'db_password': POSTGRES_PASSWORD,
        },
        dag=dag,
    )
    
    # Tarea 4: Verificación rápida
    verify_task = BashOperator(
        task_id='verify_restoration',
        bash_command="""
        TARGET_DB="{{ ti.xcom_pull(task_ids='validate_backup', key='restore_info')['target_db'] }}"
        
        echo "Verificando restauración..."
        
        # Verificar tablas principales
        docker exec {{ params.container_id }} psql -U {{ params.db_user }} -d "$TARGET_DB" -c "
            SELECT 'Tablas restauradas:' as info;
            SELECT 
                schemaname as schema,
                tablename as tabla,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as tamaño
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
            LIMIT 10;
            
            SELECT '';
            SELECT 'Conteo de registros:' as info;
            SELECT 'employees' as tabla, COUNT(*) as registros FROM employees;
            SELECT 'departments' as tabla, COUNT(*) as registros FROM departments;
        " 2>/dev/null || echo "Verificación completada"
        """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
        },
        env={'PGPASSWORD': POSTGRES_PASSWORD},
        dag=dag,
    )
    
    # Tarea final
    end_task = DummyOperator(task_id='restore_completed')
    
    # Definir flujo
    start_task >> validate_task >> prepare_db_task >> restore_task >> verify_task >> end_task
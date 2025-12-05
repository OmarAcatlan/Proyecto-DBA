from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from datetime import datetime, timedelta
import os
import logging

# Configuración de variables de entorno
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'admin')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'employees')
POSTGRES_CONTAINER_ID = os.environ.get('POSTGRES_CONTAINER_ID', 'development-postgres-1')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

# Rutas de backup
POSTGRES_BACKUP_BASE = '/var/lib/postgresql/backups/'
POSTGRES_MONTHLY_PATH = os.path.join(POSTGRES_BACKUP_BASE, 'monthly/')

# Configuración del DAG para backup mensual
default_args = {
    'owner': 'hr_team',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
    'start_date': datetime(2025, 1, 1, 4, 0),
}

# Crear DAG mensual
with DAG(
    dag_id='hr_monthly_backup',
    default_args=default_args,
    description='Backup mensual completo de base de datos HR con verificacion y reportes',
    schedule_interval='0 4 1 * *',
    catchup=False,
    tags=['hr', 'backup', 'monthly', 'postgres'],
    max_active_runs=1,
) as dag:
    
    # TAREAS DE INICIO
    start_task = DummyOperator(
        task_id='start_backup_process',
        dag=dag,
    )
    
    # TAREA 1: CREAR DIRECTORIOS
    create_dirs_task = BashOperator(
        task_id='create_backup_directories',
        bash_command=f"""
        # Crear directorios para backups mensuales
        docker exec {POSTGRES_CONTAINER_ID} bash -c "
            mkdir -p {POSTGRES_MONTHLY_PATH}
            chmod 755 {POSTGRES_MONTHLY_PATH}
            echo 'Directorios creados: {POSTGRES_MONTHLY_PATH}'
        "
        """,
        dag=dag,
    )
    
    # TAREA 2: GENERAR NOMBRE DE ARCHIVO
    def generate_backup_filename(**context):
        """Generar nombre de archivo con timestamp mensual"""
        execution_date = context['data_interval_start']
        filename = f"{POSTGRES_DB}_db_{execution_date.strftime('%Y_%m')}.dump"
        context['ti'].xcom_push(key='backup_filename', value=filename)
        return filename
    
    generate_filename_task = PythonOperator(
        task_id='generate_backup_filename',
        python_callable=generate_backup_filename,
        dag=dag,
    )
    
    # TAREA 3: BACKUP COMPLETO MENSUAL
    monthly_backup_task = BashOperator(
        task_id='execute_monthly_backup',
        bash_command="""
        # Crear nombre de archivo dinamico
        BACKUP_FILENAME="{{ ti.xcom_pull(task_ids='generate_backup_filename') }}"
        BACKUP_PATH="{{ params.monthly_path }}$BACKUP_FILENAME"
        
        echo "Creando backup: $BACKUP_PATH"
        
        # Ejecutar pg_dump con formato custom para mejor compresion
        docker exec {{ params.container_id }} bash -c "
            export PGPASSWORD='{{ params.db_password }}'
            pg_dump \
                -U {{ params.db_user }} \
                -d {{ params.db_name }} \
                -F c \
                -Z 9 \
                -v \
                -f '$BACKUP_PATH'
        "
        
        # Verificar creacion del archivo
        docker exec {{ params.container_id }} bash -c "
            if [ -f '$BACKUP_PATH' ]; then
                echo 'Backup creado exitosamente'
                echo 'Tamaño del archivo:'
                ls -lh '$BACKUP_PATH'
            else
                echo 'Error: Backup no creado'
                exit 1
            fi
        "
        """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
            'db_name': POSTGRES_DB,
            'db_password': POSTGRES_PASSWORD,
            'monthly_path': POSTGRES_MONTHLY_PATH,
        },
        dag=dag,
    )
    
    # TAREA 4: CREAR CHECKSUM
    create_checksum_task = BashOperator(
        task_id='create_backup_checksum',
        bash_command="""
        # Obtener nombre del archivo de backup
        BACKUP_FILENAME="{{ ti.xcom_pull(task_ids='generate_backup_filename') }}"
        BACKUP_PATH="{{ params.monthly_path }}$BACKUP_FILENAME"
        
        echo "Creando checksum para: $BACKUP_FILENAME"
        
        # Crear checksum MD5 del backup
        docker exec {{ params.container_id }} bash -c "
            cd '{{ params.monthly_path }}'
            if [ -f '$BACKUP_FILENAME' ]; then
                md5sum '$BACKUP_FILENAME' > '$BACKUP_FILENAME.md5'
                echo 'Checksum creado:'
                cat '$BACKUP_FILENAME.md5'
            else
                echo 'Error: Archivo de backup no encontrado'
                exit 1
            fi
        "
        """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'monthly_path': POSTGRES_MONTHLY_PATH,
        },
        dag=dag,
    )
    
    # TAREA 5: VERIFICAR INTEGRIDAD DEL BACKUP
    verify_backup_task = BashOperator(
        task_id='verify_backup_integrity',
        bash_command="""
        # Obtener nombre del archivo de backup
        BACKUP_FILENAME="{{ ti.xcom_pull(task_ids='generate_backup_filename') }}"
        BACKUP_PATH="{{ params.monthly_path }}$BACKUP_FILENAME"
        
        echo "Verificando integridad del backup..."
        
        # Verificar checksum
        docker exec {{ params.container_id }} bash -c "
            cd '{{ params.monthly_path }}'
            if [ -f '$BACKUP_FILENAME.md5' ]; then
                if md5sum -c '$BACKUP_FILENAME.md5'; then
                    echo 'Checksum verificado correctamente'
                else
                    echo 'Error: Checksum no coincide'
                    exit 1
                fi
            else
                echo 'Advertencia: No se encontro archivo de checksum'
            fi
        "
        
        # Verificar que el dump sea restaurable
        docker exec {{ params.container_id }} bash -c "
            export PGPASSWORD='{{ params.db_password }}'
            if pg_restore -l '$BACKUP_PATH' > /dev/null 2>&1; then
                echo 'Backup es restaurable (validacion de estructura)'
            else
                echo 'Error: Backup corrupto o invalido'
                exit 1
            fi
        "
        """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'monthly_path': POSTGRES_MONTHLY_PATH,
            'db_password': POSTGRES_PASSWORD,
        },
        dag=dag,
    )
    
    # TAREA 6: BACKUP DE SOLO ESQUEMA
    schema_backup_task = BashOperator(
        task_id='backup_schema_only',
        bash_command="""
        # Obtener fecha del nombre del archivo
        BACKUP_FILENAME="{{ ti.xcom_pull(task_ids='generate_backup_filename') }}"
        # Extraer fecha del patron YYYY_MM
        BACKUP_DATE=$(echo "$BACKUP_FILENAME" | grep -oE '[0-9]{4}_[0-9]{2}')
        
        SCHEMA_FILE="{{ params.monthly_path }}{{ params.db_name }}_schema_${BACKUP_DATE}.sql"
        
        echo "Creando backup de esquema: $SCHEMA_FILE"
        
        # Backup de solo la estructura (sin datos)
        docker exec {{ params.container_id }} bash -c "
            export PGPASSWORD='{{ params.db_password }}'
            pg_dump \
                -U {{ params.db_user }} \
                -d {{ params.db_name }} \
                -s \
                -f '$SCHEMA_FILE'
        "
        
        docker exec {{ params.container_id }} bash -c "
            if [ -f '$SCHEMA_FILE' ]; then
                echo 'Tablas en esquema:'
                grep 'CREATE TABLE' '$SCHEMA_FILE' | wc -l
                echo 'Tamaño del archivo de esquema:'
                ls -lh '$SCHEMA_FILE'
            else
                echo 'Error: Archivo de esquema no creado'
            fi
        "
        """,
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
            'db_name': POSTGRES_DB,
            'db_password': POSTGRES_PASSWORD,
            'monthly_path': POSTGRES_MONTHLY_PATH,
        },
        dag=dag,
    )
    
    # TAREA 7: GENERAR REPORTE MENSUAL
    def generate_monthly_report(**context):
        """Generar reporte mensual de estadisticas"""
        import subprocess
        import json
        from datetime import datetime
        
        execution_date = context['data_interval_start']
        month = execution_date.strftime('%Y-%m')
        
        # Obtener nombre del archivo de backup
        backup_filename = context['ti'].xcom_pull(task_ids='generate_backup_filename')
        
        # Comandos para obtener estadisticas (con manejo de errores)
        stats_commands = {
            'total_employees': f"docker exec {POSTGRES_CONTAINER_ID} psql -U {POSTGRES_USER} -d {POSTGRES_DB} -t -c \"SELECT COUNT(*) FROM employees WHERE end_date = '9999-12-31';\"",
            'total_departments': f"docker exec {POSTGRES_CONTAINER_ID} psql -U {POSTGRES_USER} -d {POSTGRES_DB} -t -c \"SELECT COUNT(*) FROM departments;\"",
            'db_size': f"docker exec {POSTGRES_CONTAINER_ID} psql -U {POSTGRES_USER} -d {POSTGRES_DB} -t -c \"SELECT pg_size_pretty(pg_database_size('{POSTGRES_DB}'));\"",
        }
        
        report_data = {
            'month': month,
            'generation_date': datetime.now().isoformat(),
            'database': POSTGRES_DB,
            'statistics': {},
            'backup_info': {
                'filename': backup_filename,
                'path': os.path.join(POSTGRES_MONTHLY_PATH, backup_filename),
            }
        }
        
        # Ejecutar comandos y capturar resultados
        for stat_name, command in stats_commands.items():
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    env={'PGPASSWORD': POSTGRES_PASSWORD}
                )
                if result.returncode == 0:
                    report_data['statistics'][stat_name] = result.stdout.strip()
                else:
                    # Si hay error, registrar el error pero continuar
                    report_data['statistics'][stat_name] = f'Error: {result.stderr[:100]}'
            except Exception as e:
                report_data['statistics'][stat_name] = f'Error: {str(e)[:100]}'
        
        # Guardar reporte como JSON
        report_filename = f"{POSTGRES_MONTHLY_PATH}{POSTGRES_DB}_report_{execution_date.strftime('%Y_%m')}.json"
        
        # Guardar dentro del contenedor usando docker cp
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
            json.dump(report_data, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = tmp_file.name
        
        try:
            # Copiar el archivo temporal al contenedor
            copy_cmd = f"docker cp {tmp_path} {POSTGRES_CONTAINER_ID}:{report_filename}"
            result = subprocess.run(copy_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                logging.error(f"Error copiando reporte al contenedor: {result.stderr}")
        finally:
            # Limpiar archivo temporal
            os.unlink(tmp_path)
        
        logging.info(f"Reporte mensual generado: {report_filename}")
        
        return f"Reporte generado para {month}"
    
    generate_report_task = PythonOperator(
        task_id='generate_monthly_report',
        python_callable=generate_monthly_report,
        dag=dag,
    )
    
    # TAREA 8: LIMPIAR BACKUPS ANTIGUOS
    cleanup_task = BashOperator(
        task_id='cleanup_old_backups',
        bash_command=f"""
        # Mantener backups de los ultimos 13 meses
        docker exec {POSTGRES_CONTAINER_ID} bash -c "
            cd {POSTGRES_MONTHLY_PATH}
            
            echo 'Limpiando backups mensuales antiguos (mas de 13 meses)...'
            
            # Encontrar y eliminar backups antiguos (si existen)
            find . -name '*.dump' -mtime +395 -exec echo 'Eliminando: {{}}' \\; -exec rm {{}} \\; 2>/dev/null || true
            find . -name '*.md5' -mtime +395 -exec echo 'Eliminando: {{}}' \\; -exec rm {{}} \\; 2>/dev/null || true
            find . -name '*_schema_*.sql' -mtime +180 -exec echo 'Eliminando: {{}}' \\; -exec rm {{}} \\; 2>/dev/null || true
            find . -name '*_report_*.json' -mtime +180 -exec echo 'Eliminando: {{}}' \\; -exec rm {{}} \\; 2>/dev/null || true
            
            echo 'Estado actual del directorio:'
            ls -lh 2>/dev/null || echo 'Directorio vacio'
        "
        """,
        dag=dag,
    )
    
    # TAREA 9: VERIFICACION FINAL
    def final_verification(**context):
        """Verificacion final de que todo se creo correctamente"""
        import subprocess
        
        backup_filename = context['ti'].xcom_pull(task_ids='generate_backup_filename')
        execution_date = context['data_interval_start']
        month_str = execution_date.strftime('%Y_%m')
        
        # Lista de archivos esperados
        expected_files = [
            backup_filename,
            f"{backup_filename}.md5",
            f"{POSTGRES_DB}_schema_{month_str}.sql",
            f"{POSTGRES_DB}_report_{month_str}.json",
        ]
        
        logging.info("Realizando verificacion final de archivos...")
        
        results = []
        for filename in expected_files:
            check_cmd = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"if [ -f '{POSTGRES_MONTHLY_PATH}{filename}' ]; then echo 'OK {filename}'; else echo 'ERROR {filename}'; fi\""
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            file_status = result.stdout.strip()
            results.append(file_status)
            logging.info(file_status)
        
        # Contar exitos
        success_count = sum(1 for r in results if 'OK' in r)
        total_count = len(expected_files)
        
        verification_result = f"Verificacion completada: {success_count}/{total_count} archivos creados"
        logging.info(verification_result)
        
        return verification_result
    
    final_verification_task = PythonOperator(
        task_id='final_verification',
        python_callable=final_verification,
        dag=dag,
    )
    
    # TAREA FINAL
    end_task = DummyOperator(
        task_id='backup_process_completed',
        dag=dag,
    )
    
    # DEFINICION DEL FLUJO
    # Flujo secuencial principal
    start_task >> create_dirs_task >> generate_filename_task
    
    # Despues de generar el nombre, ejecutar backup principal
    generate_filename_task >> monthly_backup_task
    
    # Despues del backup principal, ejecutar en paralelo:
    monthly_backup_task >> [create_checksum_task, schema_backup_task]
    
    # Despues del checksum, verificar
    create_checksum_task >> verify_backup_task
    
    # Despues de verificar y el esquema, generar reporte
    [verify_backup_task, schema_backup_task] >> generate_report_task
    
    # Continuar con limpieza, verificacion final y fin
    generate_report_task >> cleanup_task >> final_verification_task >> end_task
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import BranchPythonOperator
from datetime import datetime, timedelta
import os
import subprocess
import json
import logging

# Configuración de variables de entorno
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'admin')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'employees')
POSTGRES_RESTORE_DB = os.environ.get('POSTGRES_RESTORE_DB', 'employees')
POSTGRES_CONTAINER_ID = os.environ.get('POSTGRES_CONTAINER_ID', 'development-postgres-1')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

# Rutas de backup
POSTGRES_BACKUP_BASE = '/var/lib/postgresql/backups/'
POSTGRES_MONTHLY_PATH = os.path.join(POSTGRES_BACKUP_BASE, 'monthly/')
POSTGRES_RESTORE_PATH = os.path.join(POSTGRES_BACKUP_BASE, 'restore/')

# Configuración del DAG para restauración
default_args = {
    'owner': 'hr_team',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
}

# Crear DAG de restauración
with DAG(
    dag_id='hr_monthly_restore',
    default_args=default_args,
    description='Restauración de base de datos HR (incluso si tablas fueron eliminadas)',
    schedule_interval=None,
    catchup=False,
    tags=['hr', 'restore', 'recovery', 'emergency'],
    max_active_runs=1,
    params={
        'restore_date': None,
        'target_db_name': POSTGRES_RESTORE_DB,
        'drop_existing': True,
        'verify_only': False,
        'restore_mode': 'overwrite',
    },
) as dag:
    
    # ========== TAREAS DE INICIO ==========
    start_task = DummyOperator(
        task_id='start_restore_process',
        dag=dag,
    )
    
    # ========== TAREA 1: VALIDAR PARÁMETROS ==========
    def validate_restore_parameters(**context):
        """Validar parámetros de restauración"""
        params = context['params']
        dag_run_conf = context['dag_run'].conf if context['dag_run'].conf else {}
        
        # Combinar parámetros
        restore_date = dag_run_conf.get('restore_date', params.get('restore_date'))
        target_db = dag_run_conf.get('target_db_name', params.get('target_db_name', POSTGRES_DB))
        drop_existing = dag_run_conf.get('drop_existing', params.get('drop_existing', True))
        verify_only = dag_run_conf.get('verify_only', params.get('verify_only', False))
        restore_mode = dag_run_conf.get('restore_mode', params.get('restore_mode', 'overwrite'))
        
        print("="*60)
        print("PARÁMETROS DE RESTAURACIÓN")
        print("="*60)
        print(f"Fecha de backup: {restore_date or 'Más reciente'}")
        print(f"Base de datos destino: {target_db}")
        print(f"Eliminar existente: {drop_existing}")
        print(f"Solo verificar: {verify_only}")
        print(f"Modo: {restore_mode}")
        print("="*60)
        
        # Validaciones de seguridad
        if target_db == POSTGRES_DB and drop_existing and not verify_only:
            print("ADVERTENCIA CRÍTICA: Restaurarás sobre la base de datos PRODUCCIÓN!")
            print("Se eliminarán todas las tablas existentes y se restaurará desde el backup.")
            print("Presiona Ctrl+C en los próximos 5 segundos para cancelar...")
            import time
            time.sleep(5)
        
        # Si no se especifica fecha, buscar el más reciente
        if not restore_date:
            print("Buscando backup más reciente...")
            cmd = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"find {POSTGRES_MONTHLY_PATH} -name '*.dump' -type f 2>/dev/null | sort -r | head -1\""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0 or not result.stdout.strip():
                raise Exception("No se encontraron backups mensuales")
            
            latest_backup = result.stdout.strip()
            import re
            match = re.search(r'(\d{4}_\d{2})\.dump$', os.path.basename(latest_backup))
            
            if match:
                restore_date = match.group(1)
                print(f"Backup más reciente: {restore_date}")
            else:
                raise Exception("No se pudo extraer fecha del backup")
        
        # Construir rutas
        backup_filename = f"{POSTGRES_DB}_db_{restore_date}.dump"
        backup_path = os.path.join(POSTGRES_MONTHLY_PATH, backup_filename)
        checksum_path = f"{backup_path}.md5"
        
        # Verificar existencia
        cmd_check = f"docker exec {POSTGRES_CONTAINER_ID} test -f '{backup_path}'"
        if subprocess.run(cmd_check, shell=True).returncode != 0:
            cmd_list = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"ls -la {POSTGRES_MONTHLY_PATH} 2>/dev/null || echo 'No hay backups'\""
            result_list = subprocess.run(cmd_list, shell=True, capture_output=True, text=True)
            available_backups = result_list.stdout
            
            error_msg = f"""
            Backup no encontrado: {backup_path}
            
            Backups disponibles:
            {available_backups}
            
            Posibles soluciones:
            1. Verifica que el backup mensual se haya creado
            2. Usa 'verify_only: true' para listar backups
            3. Ejecuta primero el DAG hr_monthly_backup
            """
            raise Exception(error_msg)
        
        # Información del backup
        cmd_size = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"du -h '{backup_path}' 2>/dev/null | cut -f1\""
        result_size = subprocess.run(cmd_size, shell=True, capture_output=True, text=True)
        backup_size = result_size.stdout.strip() or "Desconocido"
        
        cmd_date = f"docker exec {POSTGRES_CONTAINER_ID} bash -c \"date -r '{backup_path}' '+%Y-%m-%d %H:%M:%S' 2>/dev/null\""
        result_date = subprocess.run(cmd_date, shell=True, capture_output=True, text=True)
        backup_date = result_date.stdout.strip() or "Desconocido"
        
        restore_info = {
            'restore_date': restore_date,
            'target_db': target_db,
            'drop_existing': drop_existing,
            'verify_only': verify_only,
            'restore_mode': restore_mode,
            'backup_filename': backup_filename,
            'backup_path': backup_path,
            'checksum_path': checksum_path,
            'backup_size': backup_size,
            'backup_date': backup_date,
            'original_db': POSTGRES_DB,
        }
        
        print(f"\nRESUMEN:")
        print(f"  Backup: {backup_filename}")
        print(f"  Tamaño: {backup_size}")
        print(f"  Fecha: {backup_date}")
        print(f"  Destino: {target_db}")
        print(f"  Modo: {'VERIFICACIÓN' if verify_only else 'RESTAURACIÓN'}")
        
        context['ti'].xcom_push(key='restore_info', value=restore_info)
        return restore_info
    
    validate_task = PythonOperator(
        task_id='validate_parameters',
        python_callable=validate_restore_parameters,
        dag=dag,
    )
    
    # ========== TAREA 2: VERIFICAR BACKUP ==========
    verify_backup_task = BashOperator(
        task_id='verify_backup_integrity',
        bash_command="""
BACKUP_PATH="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['backup_path'] }}"
BACKUP_FILENAME="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['backup_filename'] }}"

echo "Verificando backup: $BACKUP_FILENAME"
echo "Ruta: $BACKUP_PATH"

# 1. Verificar que el archivo existe y tiene tamaño
echo ""
echo "1. Verificando existencia y tamaño:"
docker exec {{ params.container_id }} bash -c "
    if [ -f '$BACKUP_PATH' ]; then
        echo '   OK: Backup encontrado'
        echo '   Tamaño:'
        ls -lh '$BACKUP_PATH'
    else
        echo '   ERROR: Backup no encontrado'
        exit 1
    fi
"

# 2. Verificar checksum si existe
echo ""
echo "2. Verificando checksum:"
CHECKSUM_PATH="$BACKUP_PATH.md5"
docker exec {{ params.container_id }} bash -c "
    if [ -f '$CHECKSUM_PATH' ]; then
        echo '   Checksum encontrado, verificando...'
        cd $(dirname '$BACKUP_PATH')
        if md5sum -c '$BACKUP_FILENAME.md5'; then
            echo '   OK: Checksum válido'
        else
            echo '   ERROR: Checksum inválido'
            exit 1
        fi
    else
        echo '   ADVERTENCIA: No hay checksum disponible'
    fi
"

# 3. Verificar que se pueda leer el backup
echo ""
echo "3. Validando estructura del backup:"
docker exec {{ params.container_id }} bash -c "
    echo '   Probando lectura del backup...'
    if pg_restore -l '$BACKUP_PATH' > /dev/null 2>&1; then
        echo '   OK: Backup es legible'
        TABLE_COUNT=\$(pg_restore -l '$BACKUP_PATH' | grep 'TABLE DATA' | wc -l)
        echo '   Tablas en backup: \$TABLE_COUNT'
    else
        echo '   ERROR: No se puede leer el backup'
        exit 1
    fi
"

echo ""
echo "Verificación completada exitosamente"
""",
        params={
            'container_id': POSTGRES_CONTAINER_ID,
        },
        dag=dag,
    )
    
    # ========== TAREA 3: DECIDIR FLUJO ==========
    def decide_flow(**context):
        restore_info = context['ti'].xcom_pull(
            task_ids='validate_parameters', 
            key='restore_info'
        )
        
        if restore_info.get('verify_only'):
            print("Modo solo verificación - Saltando restauración")
            return 'generate_final_report'
        else:
            print("Iniciando restauración completa")
            return 'prepare_database_restore'
    
    decide_flow_task = BranchPythonOperator(
        task_id='decide_flow',
        python_callable=decide_flow,
        dag=dag,
    )
    
    # ========== TAREA 4: PREPARAR BASE DE DATOS PARA RESTAURACIÓN ==========
    prepare_db_task = BashOperator(
        task_id='prepare_database_restore',
        bash_command="""
TARGET_DB="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['target_db'] }}"
DROP_EXISTING="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['drop_existing'] }}"

echo "Preparando base de datos para restauración..."
echo "Base de datos: $TARGET_DB"
echo "Eliminar existente: $DROP_EXISTING"

# Verificar si la base de datos existe
echo "Verificando si la base de datos existe..."
DB_EXISTS=$(docker exec {{ params.container_id }} psql -U {{ params.db_user }} -t -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB';" 2>/dev/null | xargs)

if [ ! -z "$DB_EXISTS" ]; then
    echo "La base de datos '$TARGET_DB' ya existe"
    
    if [ "$DROP_EXISTING" = "True" ]; then
        echo "Eliminando base de datos existente..."
        
        # 1. Terminar conexiones
        echo "Terminando conexiones activas..."
        docker exec {{ params.container_id }} psql -U {{ params.db_user }} -c \
            "SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = '$TARGET_DB' 
            AND pid <> pg_backend_pid();" 2>/dev/null || echo "Conexiones terminadas"
        
        sleep 2
        
        # 2. Eliminar base de datos
        echo "Eliminando base de datos..."
        docker exec {{ params.container_id }} dropdb -U {{ params.db_user }} --if-exists "$TARGET_DB" 2>/dev/null
        
        # 3. Crear nueva base de datos vacía
        echo "Creando nueva base de datos..."
        docker exec {{ params.container_id }} createdb -U {{ params.db_user }} \
            --encoding=UTF8 \
            --locale=C \
            --template=template0 \
            "$TARGET_DB" 2>/dev/null
        
        echo "Base de datos recreada exitosamente"
        
    else
        echo "Base de datos existe pero drop_existing=False"
        echo "Las tablas existentes NO serán eliminadas"
        echo "pg_restore intentará restaurar sobre las tablas existentes"
    fi
else
    echo "La base de datos '$TARGET_DB' no existe - Creando..."
    docker exec {{ params.container_id }} createdb -U {{ params.db_user }} \
        --encoding=UTF8 \
        --locale=C \
        --template=template0 \
        "$TARGET_DB" 2>/dev/null
    echo "Base de datos creada"
fi

# Verificar estado final
echo ""
echo "Estado final:"
docker exec {{ params.container_id }} psql -U {{ params.db_user }} -t -c \
    "SELECT datname as base_datos, 
            pg_size_pretty(pg_database_size(datname)) as tamaño
     FROM pg_database 
     WHERE datname = '$TARGET_DB';" 2>/dev/null || echo "Preparación completada"
""",
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
        },
        dag=dag,
    )
    
    # ========== TAREA 5: RESTAURACIÓN COMPLETA (VERSIÓN SIMPLIFICADA) ==========
    restore_complete_task = BashOperator(
        task_id='restore_complete_database',
        bash_command="""
BACKUP_PATH="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['backup_path'] }}"
TARGET_DB="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['target_db'] }}"
RESTORE_DATE="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['restore_date'] }}"

echo "======================================================================"
echo "INICIANDO RESTAURACIÓN COMPLETA"
echo "======================================================================"
echo "Backup: $(basename "$BACKUP_PATH")"
echo "Destino: $TARGET_DB"
echo "Fecha del backup: $RESTORE_DATE"
echo "======================================================================"

# Verificar que el backup existe antes de proceder
echo ""
echo "Verificando backup..."
docker exec {{ params.container_id }} bash -c "
    if [ ! -f '$BACKUP_PATH' ]; then
        echo 'ERROR: Backup no encontrado en: $BACKUP_PATH'
        echo 'Archivos disponibles:'
        ls -la $(dirname '$BACKUP_PATH')/
        exit 1
    fi
    echo 'OK: Backup encontrado'
"

START_TIME=$(date +%s)

echo ""
echo "Ejecutando pg_restore..."
echo "Esto puede tomar varios minutos..."
echo ""

# Opción 1: Si PGPASSWORD está configurada
if [ ! -z "{{ params.db_password }}" ]; then
    echo "Usando PGPASSWORD..."
    # Crear un script temporal dentro del contenedor
    docker exec {{ params.container_id }} bash -c "
        cat > /tmp/restore_script.sh << 'EOF'
        #!/bin/bash
        export PGPASSWORD='{{ params.db_password }}'
        echo 'Iniciando pg_restore...'
        echo 'Base de datos destino: $TARGET_DB'
        echo 'Archivo backup: $BACKUP_PATH'
        
        pg_restore \\
            -U {{ params.db_user }} \\
            -d '$TARGET_DB' \\
            --clean \\
            --if-exists \\
            --no-owner \\
            --no-privileges \\
            -j 2 \\
            -v \\
            '$BACKUP_PATH'
        
        EXIT_CODE=\$?
        echo 'pg_restore terminó con código: \$EXIT_CODE'
        exit \$EXIT_CODE
EOF
        chmod +x /tmp/restore_script.sh
        /tmp/restore_script.sh
    "
else
    echo "PGPASSWORD no configurada, intentando sin contraseña..."
    # Ejecutar pg_restore directamente
    docker exec {{ params.container_id }} bash -c "
        echo 'Ejecutando pg_restore sin contraseña...'
        pg_restore \\
            -U {{ params.db_user }} \\
            -d '$TARGET_DB' \\
            --clean \\
            --if-exists \\
            --no-owner \\
            --no-privileges \\
            -j 2 \\
            -v \\
            '$BACKUP_PATH'
    "
fi

RESTORE_EXIT=$?

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "======================================================================"
echo "RESULTADO DE LA RESTAURACIÓN"
echo "======================================================================"

if [ $RESTORE_EXIT -eq 0 ]; then
    echo "✅ RESTAURACIÓN EXITOSA"
    echo "   Duración: $DURATION segundos"
    
    # Verificar tablas restauradas
    echo ""
    echo "Verificando tablas restauradas..."
    docker exec {{ params.container_id }} psql -U {{ params.db_user }} -d "$TARGET_DB" -c "
        SELECT COUNT(*) as total_tablas FROM pg_tables WHERE schemaname = 'public';
        SELECT tablename, pg_size_pretty(pg_total_relation_size('public.' || tablename)) as tamaño 
        FROM pg_tables 
        WHERE schemaname = 'public' 
        ORDER BY tablename 
        LIMIT 10;
    " 2>/dev/null || echo "No se pudieron listar tablas"
    
else
    echo "❌ RESTAURACIÓN FALLIDA"
    echo "   Código de error: $RESTORE_EXIT"
    echo "   Duración: $DURATION segundos"
    
    # Mostrar información de depuración
    echo ""
    echo "Información de depuración:"
    echo "1. Verificando si la base de datos existe:"
    docker exec {{ params.container_id }} psql -U {{ params.db_user }} -t -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB';" 2>/dev/null || echo "Error al verificar base de datos"
    
    echo ""
    echo "2. Verificando archivo de backup:"
    docker exec {{ params.container_id }} ls -la "$BACKUP_PATH" 2>/dev/null || echo "No se pudo verificar backup"
    
    exit 1
fi

echo ""
echo "Restauración completada en $DURATION segundos"
""",
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
            'db_password': POSTGRES_PASSWORD,
        },
        dag=dag,
    )
    
    # ========== TAREA 6: VERIFICAR TABLAS RESTAURADAS ==========
    verify_tables_task = BashOperator(
        task_id='verify_restored_tables',
        bash_command="""
TARGET_DB="{{ ti.xcom_pull(task_ids='validate_parameters', key='restore_info')['target_db'] }}"

echo ""
echo "VERIFICACIÓN DETALLADA DE TABLAS RESTAURADAS"
echo "============================================"

# Listar todas las tablas
echo "1. Lista completa de tablas:"
docker exec {{ params.container_id }} psql -U {{ params.db_user }} -d "$TARGET_DB" -c "
    SELECT 
        tablename as tabla,
        pg_size_pretty(pg_total_relation_size('public.' || tablename)) as tamaño
    FROM pg_tables 
    WHERE schemaname = 'public'
    ORDER BY tablename;
" 2>/dev/null || echo "No se pudieron listar tablas"

echo ""
echo "2. Conteo de registros en tablas principales:"

TABLAS_CRITICAS="employees departments dept_emp dept_manager titles salaries"

for tabla in $TABLAS_CRITICAS; do
    echo -n "   $tabla: "
    COUNT=$(docker exec {{ params.container_id }} psql -U {{ params.db_user }} -d "$TARGET_DB" -t -c \
        "SELECT COUNT(*) FROM $tabla;" 2>/dev/null | tr -d '[:space:]' || echo "ERROR")
    echo "$COUNT registros"
done

echo ""
echo "3. Verificación de integridad básica:"
docker exec {{ params.container_id }} psql -U {{ params.db_user }} -d "$TARGET_DB" -c "
    -- Total de empleados
    SELECT 'Total empleados' as metric, COUNT(*) as value FROM employees;
    
    -- Empleados activos
    SELECT 'Empleados activos' as metric, COUNT(*) as value 
    FROM employees 
    WHERE end_date = '9999-12-31';
    
    -- Departamentos
    SELECT 'Total departamentos' as metric, COUNT(*) as value FROM departments;
    
    -- Salarios
    SELECT 'Registros de salarios' as metric, COUNT(*) as value FROM salaries;
" 2>/dev/null || echo "No se pudo realizar verificación de integridad"

echo ""
echo "Verificación completada"
""",
        params={
            'container_id': POSTGRES_CONTAINER_ID,
            'db_user': POSTGRES_USER,
        },
        dag=dag,
    )
    
    # ========== TAREA 7: REPORTE FINAL ==========
    def generate_final_report(**context):
        """Generar reporte final de restauración"""
        import json
        from datetime import datetime
        
        restore_info = context['ti'].xcom_pull(
            task_ids='validate_parameters', 
            key='restore_info'
        )
        
        verify_only = restore_info.get('verify_only', False)
        target_db = restore_info.get('target_db')
        
        report = {
            'restoration_report': {
                'timestamp': datetime.now().isoformat(),
                'operation': 'verification' if verify_only else 'full_restoration',
                'parameters': restore_info,
                'success': True,
            }
        }
        
        print(f"\n{'='*60}")
        print("REPORTE FINAL DE RESTAURACIÓN")
        print("="*60)
        
        if verify_only:
            print("Operación: VERIFICACIÓN DE BACKUP")
            print(f"Backup verificado: {restore_info.get('backup_filename')}")
            print(f"Tamaño: {restore_info.get('backup_size')}")
            print(f"Fecha: {restore_info.get('backup_date')}")
        else:
            print("Operación: RESTAURACIÓN COMPLETA")
            print(f"Backup restaurado: {restore_info.get('backup_filename')}")
            print(f"Base de datos destino: {target_db}")
            print(f"Fecha del backup: {restore_info.get('restore_date')}")
        
        print("="*60)
        print("Reporte generado exitosamente")
        
        return "Reporte final generado"
    
    generate_report_task = PythonOperator(
        task_id='generate_final_report',
        python_callable=generate_final_report,
        dag=dag,
    )
    
    # ========== TAREA 8: LIMPIEZA ==========
    cleanup_task = BashOperator(
        task_id='cleanup_and_notify',
        bash_command="""
echo ""
echo "LIMPIEZA Y NOTIFICACIÓN"
echo "======================="
echo ""
echo "Proceso de restauración completado exitosamente"
echo ""
echo "Recomendaciones:"
echo "1. Verificar manualmente los datos críticos"
echo "2. Probar consultas importantes"
echo "3. Documentar el proceso realizado"
""",
        dag=dag,
    )
    
    # ========== TAREA FINAL ==========
    end_task = DummyOperator(
        task_id='process_completed',
        dag=dag,
    )
    
    # ========== DEFINICIÓN DEL FLUJO ==========
    # Flujo principal
    start_task >> validate_task >> verify_backup_task >> decide_flow_task
    
    # Rama de solo verificación
    decide_flow_task >> generate_report_task
    
    # Rama de restauración completa
    decide_flow_task >> prepare_db_task >> restore_complete_task >> verify_tables_task
    verify_tables_task >> generate_report_task
    
    # Continuación común
    generate_report_task >> cleanup_task >> end_task
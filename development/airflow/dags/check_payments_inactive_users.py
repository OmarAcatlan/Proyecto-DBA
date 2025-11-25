from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import pandas as pd
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT", 587)) 
sender_email = os.getenv("SENDER_EMAIL")
sender_password = os.getenv("SENDER_PASSWORD")
receiver_emails = os.getenv("RECEIVER_EMAILS", "")
connection_id = os.getenv("AIRFLOW_CONN_ID")
receiver_emails = [email.strip() for email in receiver_emails.split(",") if email.strip()]

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10)
}

def check_payments_to_inactive_employees():
    """
    Verifica pagos a empleados que tienen end_date menor a la fecha de pago
    """
    hook = PostgresHook(postgres_conn_id=connection_id)
    
    query = """
    SELECT 
        eph.payment_id,
        eph.emp_no,
        e.first_name,
        e.last_name,
        e.end_date as employee_end_date,
        eph.payment_date,
        eph.salary_amount,
        eph.from_date as payment_from_date,
        eph.to_date as payment_to_date
    FROM employee_payment_history eph
    JOIN employees e ON eph.emp_no = e.emp_no
    WHERE eph.payment_date > e.end_date
        OR eph.from_date > e.end_date
    ORDER BY eph.payment_date DESC;
    """
    
    df = hook.get_pandas_df(query)
    
    if not df.empty:
        # Generar alerta
        send_alert_email(df, "ALERTA: Pagos a Empleados Inactivos")
        
        # También podrías registrar esto en una tabla de auditoría
        log_audit_event(df)
        
        print(f"ALERTA: Se encontraron {len(df)} pagos a empleados inactivos")
        return False  # Podría hacer fallar el DAG si es crítico
    else:
        print("No se encontraron pagos a empleados inactivos")
        return True

def send_alert_email(df, subject):
    """
    Envía alerta por correo electrónico
    """
    smtp_server = smtp_server
    smtp_port = smtp_port
    sender_email = sender_email
    sender_password = sender_password
    receiver_emails = receiver_emails
    
    msg = MIMEMultipart()
    msg['Subject'] = f"URGENTE: {subject}"
    msg['From'] = sender_email
    msg['To'] = ", ".join(receiver_emails)
    
    # Crear tabla HTML para el email
    html_table = df.to_html(index=False, classes='table table-striped')
    
    body = f"""
    <html>
    <body>
        <h2>ALERTA CRÍTICA</h2>
        <p>Se han detectado <strong>{len(df)} pagos</strong> realizados a empleados que ya no están activos en la empresa.</p>
        
        <h3>Detalles de los pagos:</h3>
        {html_table}
        
        <p><strong>Acción requerida:</strong> Revisar inmediatamente estos pagos y tomar las acciones correctivas necesarias.</p>
        
        <br>
        <p>Sistema de Auditoría de Pagos</p>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(body, 'html'))
    
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)

def log_audit_event(df):
    """
    Registra el evento de auditoría en una tabla
    """
    hook = PostgresHook(postgres_conn_id='your_postgres_conn')
    
    for _, row in df.iterrows():
        insert_query = """
        INSERT INTO payment_audit_log 
        (payment_id, emp_no, audit_type, description, audit_date)
        VALUES (%s, %s, 'INACTIVE_EMPLOYEE_PAYMENT', 
                'Pago detectado para empleado inactivo', NOW())
        """
        hook.run(insert_query, parameters=(row['payment_id'], row['emp_no']))

with DAG(
    'inactive_employee_payment_check',
    default_args=default_args,
    description='Verifica pagos a empleados inactivos',
    schedule_interval='0 8 * * 1-5',  # Ejecutar días laborables a las 8 AM
    catchup=False,
    tags=['payments', 'audit', 'compliance']
) as dag:
    
    check_inactive_payments_task = PythonOperator(
        task_id='check_payments_to_inactive_employees',
        python_callable=check_payments_to_inactive_employees
    )
    
    check_inactive_payments_task
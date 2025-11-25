from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import os


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
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

def check_excessive_payments():
    """
    Verifica si algún empleado recibe más de 2 veces su salario en pagos
    """
    hook = PostgresHook(postgres_conn_id=connection_id)
    
    query = """
    WITH employee_avg_salary AS (
        SELECT 
            e.emp_no,
            AVG(s.salary) as avg_salary
        FROM employees e
        JOIN salaries s ON e.emp_no = s.emp_no
        WHERE s.to_date = '9999-12-31'
        GROUP BY e.emp_no
    ),
    total_monthly_payments AS (
        SELECT 
            eph.emp_no,
            SUM(eph.salary_amount) as total_payments,
            e.first_name,
            e.last_name
            FROM employee_payment_history eph
        JOIN employees e ON eph.emp_no = e.emp_no
        WHERE eph.payment_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
            AND eph.payment_date < DATE_TRUNC('month', CURRENT_DATE)
        GROUP BY eph.emp_no, e.first_name, e.last_name
    )
    SELECT 
        tmp.emp_no,
        tmp.first_name,
        tmp.last_name,
        eas.avg_salary,
        tmp.total_payments,
        (tmp.total_payments / eas.avg_salary) as payment_ratio
    FROM total_monthly_payments tmp
    JOIN employee_avg_salary eas ON tmp.emp_no = eas.emp_no
    WHERE (tmp.total_payments / eas.avg_salary) > 2
    ORDER BY payment_ratio DESC;
    """
    
    df = hook.get_pandas_df(query)
    
    if not df.empty:
        # Generar reporte Excel
        report_path = f"/tmp/excessive_payments_report_{datetime.now().strftime('%Y%m%d')}.xlsx"
        df.to_excel(report_path, index=False)
        
        # Enviar email con el reporte
        send_email_with_report(df, report_path, "Reporte de Pagos Excesivos")
        
        print(f"Se encontraron {len(df)} empleados con pagos excesivos")
    else:
        print("No se encontraron empleados con pagos excesivos")

def send_email_with_report(df, report_path, subject):
    """
    Envía el reporte por correo electrónico
    """

    smtp_server = smtp_server
    smtp_port = smtp_port
    sender_email = sender_email
    sender_password = sender_password
    receiver_emails = receiver_emails
    
    # Crear mensaje
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = ", ".join(receiver_emails)
    
    # Cuerpo del mensaje
    body = f"""
    Se han identificado {len(df)} empleados con pagos que exceden el doble de su salario.
    
    Adjunto el reporte detallado.
    
    Saludos,
    Sistema de Historial de pagos de nomina
    """
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Adjuntar archivo
    with open(report_path, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
    
    encoders.encode_base64(part)
    part.add_header(
        'Content-Disposition',
        f'attachment; filename= {os.path.basename(report_path)}'
    )
    msg.attach(part)
    
    # Enviar email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)

with DAG(
    'monthly_payment_excess_check',
    default_args=default_args,
    description='Verifica pagos que exceden el doble del salario mensualmente',
    schedule_interval='0 0 1 * *',  # Ejecutar el día 1 de cada mes
    catchup=False,
    tags=['payments', 'monitoring']
) as dag:
    
    check_payments_task = PythonOperator(
        task_id='check_excessive_payments',
        python_callable=check_excessive_payments
    )
    
    check_payments_task
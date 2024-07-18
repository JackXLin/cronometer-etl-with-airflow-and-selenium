from airflow.decorators import dag, task
from datetime import timedelta, datetime
from process_csv import process_csv as process_csv_func
from visualisation import visualise_data as visualise_data_func
from upload_s3 import upload_to_s3 as upload_to_s3_func
from fetch_cronometer import cronometer_export as cronometer_export_func
from remove_old_file import remove_old_files as remove_old_files_func

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

@dag(default_args=default_args, schedule_interval='@daily', start_date=datetime(2023,1,1), catchup=False)
def csv_processing_dag():

    @task
    def remove_files():
        remove_old_files_func()

    @task
    def fetch_cronometer_data():
        cronometer_export_func()

    @task
    def process_csv(file_path1: str, file_path2: str):
        return process_csv_func(file_path1, file_path2)

    @task
    def visualise_data(file_path: str):
        return visualise_data_func(file_path)

    @task
    def upload_to_s3(file_path: str, bucket_name: str):
        return upload_to_s3_func(file_path, bucket_name)

    # Paths to the CSV files
    file_path1 = '/opt/airflow/csvs/dailysummary.csv'
    file_path2 = '/opt/airflow/csvs/biometrics.csv'

    # Task dependencies
    remove_task = remove_files()
    fetch_task = fetch_cronometer_data()
    process_task = process_csv(file_path1, file_path2)
    visualisation_task = visualise_data(process_task)
    upload_task = upload_to_s3(visualisation_task, 'airflow-cronometer')

    remove_task >> fetch_task >> process_task >> visualisation_task >> upload_task

dag_instance = csv_processing_dag()

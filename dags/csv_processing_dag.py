from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from datetime import timedelta
from process_csv import process_csv as process_csv_func
from visualisation import visualise_data as visualise_data_func
from upload_s3 import upload_to_s3 as upload_to_s3_func

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

@dag(default_args=default_args, schedule_interval='@daily', start_date=days_ago(1), catchup=False, tags=['example'])
def csv_processing_dag():
    
    @task
    def process_csv(file_path1: str, file_path2: str):
        return process_csv_func(file_path1, file_path2)

    @task
    def visualise_data(file_path: str):
        return visualise_data_func(file_path)

    @task
    def upload_to_s3(file_path: str, bucket_name: str):
        return upload_to_s3_func(file_path, bucket_name)

    file_path1 = '/opt/airflow/csvs/dailysummary.csv'
    file_path2 = '/opt/airflow/csvs/biometrics.csv'
    cleaned_file_path = process_csv(file_path1, file_path2)
    visualisation_path = visualise_data(cleaned_file_path)
    upload_to_s3(visualisation_path, 'airflow-cronometer')

dag_instance = csv_processing_dag()

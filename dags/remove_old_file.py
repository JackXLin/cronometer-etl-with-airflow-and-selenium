import os

def remove_old_files():
    download_dir = "/opt/airflow/csvs"
    file_path_biometrics = os.path.join(download_dir, 'biometrics.csv')
    file_path_dailysummary = os.path.join(download_dir, 'dailysummary.csv')
    file_path_processed = os.path.join(download_dir, 'processed_data.csv')
    
    if os.path.exists(file_path_biometrics):
        os.remove(file_path_biometrics)
    
    if os.path.exists(file_path_dailysummary):
        os.remove(file_path_dailysummary)
    
    if os.path.exists(file_path_processed):
        os.remove(file_path_processed)
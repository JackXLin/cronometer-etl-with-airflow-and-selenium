import os

def remove_old_files():
    download_dir = "/opt/airflow/csvs"
    file_path_biometrics = os.path.join(download_dir, 'biometrics.csv')
    file_path_dailysummary = os.path.join(download_dir, 'dailysummary.csv')
    file_path_garmin = os.path.join(download_dir, 'garmin_daily.csv')
    file_path_garmin_activities = os.path.join(download_dir, 'garmin_activities.csv')
    file_path_garmin_heart_rate = os.path.join(download_dir, 'garmin_heart_rate_detail.csv')
    file_path_processed = os.path.join(download_dir, 'processed_data.csv')
    
    if os.path.exists(file_path_biometrics):
        os.remove(file_path_biometrics)
    
    if os.path.exists(file_path_dailysummary):
        os.remove(file_path_dailysummary)

    if os.path.exists(file_path_garmin):
        os.remove(file_path_garmin)
    
    if os.path.exists(file_path_garmin_activities):
        os.remove(file_path_garmin_activities)

    if os.path.exists(file_path_garmin_heart_rate):
        os.remove(file_path_garmin_heart_rate)
    
    if os.path.exists(file_path_processed):
        os.remove(file_path_processed)
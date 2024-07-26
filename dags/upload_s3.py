import boto3
import datetime
import os

def upload_to_s3(file_path, bucket):
    """Upload a single file to an S3 bucket within a folder named after the current date

    :param file_path: File to upload
    :param bucket: Bucket to upload to
    :return: True if the file was uploaded successfully, else False
    """
    s3_client = boto3.client('s3')
    success = True

    # Check if the file exists
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return False

    # Get the current date in YYYY-MM-DD format
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')

    # Create the object name with the folder structure
    object_name = f"{current_date}/{os.path.basename(file_path)}"  # This ensures the file is stored in the date-named folder
    try:
        s3_client.upload_file(file_path, bucket, object_name)
        print(f"File {file_path} uploaded to {bucket}/{current_date} successfully.")
    except Exception as e:
        print(f"Failed to upload {file_path} to {bucket}/{current_date}. Error: {e}")
        success = False

    return success

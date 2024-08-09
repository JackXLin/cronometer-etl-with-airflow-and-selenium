
# Cronometer ETL Pipeline with Apache Airflow and Selenium

This project sets up an automated ETL (Extract, Transform, Load) pipeline using Apache Airflow and Selenium. The pipeline logs into Cronometer, exports daily nutrition data, processes the data, visualises it, and uploads the visualisation to Amazon S3.

## Table of Contents

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
    - [Method 1: Using AWS CLI](#method-1-using-aws-cli)
    - [Method 2: Using Environment Variables](#method-2-using-environment-variables)
4. [Running the Docker Containers](#running-the-docker-containers)
5. [DAG Configuration](#dag-configuration)
6. [Automating Cronometer Data Export](#automating-cronometer-data-export)
7. [Conclusion](#conclusion)

## Introduction

This project demonstrates setting up an automated data pipeline using Apache Airflow and Selenium to collect, process, visualise, and store data from Cronometer.

## Prerequisites

- Docker
- Cronometer account
- Python 3.6+
- Apache Airflow
- Selenium
- Boto3 (for S3 interactions)
- Pandas
- Matplotlib
- dotenv (for environment variables)

## Setup

### Method 1: Using AWS CLI

Configure AWS CLI with your credentials:

```sh
aws configure
```

### Method 2: Using Environment Variables

Add the following to your `docker-compose.yml`:

```yaml
environment:
  AWS_ACCESS_KEY_ID: your-access-key-id
  AWS_SECRET_ACCESS_KEY: your-secret-access-key
  AWS_DEFAULT_REGION: your-region
```

## Running the Docker Containers

Build and run the Docker containers:

```bash
docker-compose build
docker-compose up -d
```

## DAG Configuration

Create a DAG to automate the entire process. The DAG should include tasks for:

1. Fetching the CSV data from Cronometer.
2. Processing the CSV data.
3. Visualising the processed data.
4. Uploading the visualisation to S3.

## Automating Cronometer Data Export

### fetch_cronometer.py

This script logs into Cronometer and exports daily nutrition data using Selenium.

#### Input Parameters
- `username` (string): Your Cronometer username.
- `password` (string): Your Cronometer password.

#### Expected Outputs
- A CSV file containing the exported daily nutrition data downloaded to the specified directory.

#### Example Usage

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from cronometer_credential import username, password
import time

# Initialize WebDriver
driver = webdriver.Firefox()

# Login to Cronometer
driver.get("https://www.cronometer.com/login/")
wait = WebDriverWait(driver, 20)
email_field = wait.until(EC.visibility_of_element_located((By.ID, "username")))
password_field = wait.until(EC.visibility_of_element_located((By.ID, "password")))
submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[span[@id="login_txt"]]')))
email_field.send_keys(username)
password_field.send_keys(password)
submit_button.click()

# Navigate to Export Data
more_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='More']")))
more_button.click()
account_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@href='#account']")))
account_link.click()
export_data_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Export Data']")))
driver.execute_script("arguments[0].click();", export_data_button)
export_daily_nutrition_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Export Daily Nutrition")]')))
driver.execute_script("arguments[0].click();", export_daily_nutrition_button)

# Wait for download to complete
time.sleep(20)

driver.quit()
```

### process_csv.py

This script processes the downloaded CSV file.

#### Input Parameters
- `file_path` (string): Path to the CSV file.

#### Expected Outputs
- Processed CSV file saved to the specified directory.

#### Example Usage

```python
import pandas as pd

def process_csv(file_path):
    df = pd.read_csv(file_path)
    # Perform processing
    processed_df = df.dropna()
    processed_df.to_csv('processed_file.csv', index=False)

process_csv('downloaded_file.csv')
```

### visualise_data.py

This script creates a visualisation from the processed data.

#### Input Parameters
- `file_path` (string): Path to the processed CSV file.

#### Expected Outputs
- PNG file containing the visualisation saved to the specified directory.

#### Example Usage

```python
import pandas as pd
import matplotlib.pyplot as plt

def visualise_data(file_path):
    df = pd.read_csv(file_path)
    plt.plot(df['Date'], df['Weight (kg)'])
    plt.savefig('visualisation.png')

visualise_data('processed_file.csv')
```

### upload_to_s3.py

This script uploads the visualisation to an S3 bucket.

#### Input Parameters
- `file_path` (string): Path to the PNG file.
- `bucket_name` (string): Name of the S3 bucket.

#### Expected Outputs
- PNG file uploaded to the specified S3 bucket.

#### Example Usage

```python
import boto3

def upload_to_s3(file_path, bucket_name):
    s3_client = boto3.client('s3')
    s3_client.upload_file(file_path, bucket_name, file_path)

upload_to_s3('visualisation.png', 'your-bucket-name')
```

## Conclusion

This `README.md` provides an overview of setting up an automated data pipeline using Apache Airflow to collect, process, visualise, and store data from Cronometer. Follow the steps to configure your environment, set up Airflow, automate data export, and run your data pipeline.

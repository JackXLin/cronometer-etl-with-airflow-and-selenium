
# Cronometer ETL Pipeline with Apache Airflow and Selenium

This project sets up an automated ETL (Extract, Transform, Load) pipeline using Apache Airflow and Selenium. The pipeline logs into Cronometer, exports daily nutrition data, optionally fetches Garmin Connect daily metrics, processes the data, visualises it, and uploads the visualisation to Amazon S3.

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
- Pydantic
- dotenv (for environment variables)
- Optional: Garmin Connect account for wearable metrics

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

### Optional Garmin Connect Integration

If you want to enrich the processed dataset with Garmin daily metrics such as steps, distance, active calories, sleep duration and sleep score, stress, body battery, resting heart rate, HRV, respiration, SpO2, training readiness, training status, activity counts, and intensity minutes:

1. Copy `.env.example` to `.env`.
2. Set `GARMIN_ENABLED=true` so the DAG merges Garmin data into `processed_data.csv` and the PDF report. Keep this enabled even if you have already pre-seeded the Garmin CSV artifacts manually.
3. Fill in `GARMIN_EMAIL` and `GARMIN_PASSWORD` only when you need to run the one-time bootstrap helper or refresh expired Garmin tokens.
4. Leave `GARMINTOKENS` pointed at `/opt/airflow/config/garmin_tokens` unless you have a different mounted token location.
5. Set `GARMIN_HISTORICAL_START_DATE` to the first day you want included in the first API backfill when no Garmin history has already been pre-seeded.
6. Leave `GARMIN_SYNC_OVERLAP_DAYS=2` unless you want a larger overlap window for late Garmin corrections.
7. Use `GARMIN_FORCE_FULL_REFRESH=true` only when you want the next run to rebuild the Garmin store from scratch, then return it to `false`.
8. Keep `GARMIN_LOOKBACK_DAYS` only as a legacy fallback when `GARMIN_HISTORICAL_START_DATE` is not configured.
9. Install the Python dependencies in `requirements.txt`, which now include `pydantic` for Garmin activity/detail row validation.

## Running the Docker Containers

Build and run the Docker containers:

```bash
docker compose up -d --build
```

## Garmin Token Bootstrap

Garmin ingestion uses a manual bootstrap token model:

1. Start the Airflow environment so the Python dependencies are available.
2. Open a shell in an Airflow container.
3. Run the bootstrap entrypoint:

```bash
python /opt/airflow/dags/garmin_auth_bootstrap.py
```

4. Complete the Garmin login and MFA prompt once.
5. Confirm that token files were written under `GARMINTOKENS` (default: `/opt/airflow/config/garmin_tokens`).

example command:
```bash
docker compose run --rm airflow-cli python /opt/airflow/dags/garmin_auth_bootstrap.py
```

After that, scheduled DAG runs reuse the saved Garmin session non-interactively from `GARMINTOKENS`. `GARMIN_EMAIL` and `GARMIN_PASSWORD` are only needed when you run the bootstrap helper again.

Garmin extraction writes the following artifacts under `/opt/airflow/csvs`:

- `garmin_daily.csv` for flattened day-level Garmin metrics and weekly rollups.
- `garmin_activities.csv` for normalized Garmin activity-session rows.
- `garmin_heart_rate_detail.csv` for normalized intraday heart-rate detail rows.

If you already have a Garmin bulk export under the repository `garmin_data/` folder, you can seed those same mounted-volume artifacts before relying on live API syncs:

```bash
python dags/garmin_export_import.py --export-root garmin_data --output-path "C:\Users\Jack\Downloads\garmin_daily.csv"
```

This standalone CLI is not part of the scheduled DAG. It writes `garmin_daily.csv`, `garmin_activities.csv`, and `garmin_heart_rate_detail.csv` into the host path that is mounted into Airflow as `/opt/airflow/csvs`, so later DAG runs can continue from that historical store.
Keep `GARMIN_ENABLED=true` if you want the DAG to merge the seeded Garmin data into `processed_data.csv` and the downstream report pages.
The current JSON importer fills daily metrics and activity sessions, but it leaves `garmin_heart_rate_detail.csv` empty until a compatible historical intraday heart-rate export source is identified.

Garmin sync now behaves as follows:

- Without a pre-seeded Garmin store, the first API-based DAG run backfills from `GARMIN_HISTORICAL_START_DATE` through today.
- After a manual historical seed or any earlier Garmin sync, the DAG reads the latest stored Garmin date and re-fetches from `last_stored_date - GARMIN_SYNC_OVERLAP_DAYS` through today.
- Garmin artifacts are preserved across DAG runs, so the mounted CSV directory now acts as the historical Garmin store.
- The initial API historical backfill can take much longer than later daily syncs because Garmin extraction queries multiple endpoint families per day.
- If you need to rebuild the Garmin store, set `GARMIN_FORCE_FULL_REFRESH=true` for one run and then return it to `false`.

When Garmin columns are present in the processed dataset, the PDF report also adds a Garmin section with:

- A Garmin context page with weekly activity summary, sleep and stress trends, body battery / resting-heart-rate context, and adherence insights.
- A Garmin-adjusted TDEE context page.
- Garmin lag heatmaps against daily and trend-based weight change.
- Weight-spike attribution diagnostics and recovery-vs-scale-noise scatter plots.
- A weekly energy-balance dashboard.
- Activity-type contribution summaries and detailed activity-session tables.
- Recovery regime comparison tables and monthly calendar / coverage views.

## DAG Configuration

Create a DAG to automate the entire process. The DAG should include tasks for:

1. Fetching the CSV data from Cronometer.
2. Optionally fetching or incrementally refreshing Garmin daily data when `GARMIN_ENABLED=true`.
3. Processing the CSV data.
4. Visualising the processed data.
5. Uploading the visualisation to S3.

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

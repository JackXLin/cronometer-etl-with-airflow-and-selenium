# Airflow Cronometer Data Pipeline

## Overview

This project automates the process of collecting, processing, visualising, and storing data from Cronometer using Apache Airflow. The pipeline consists of three main stages:

1. **Data Collection**: Automating the export of CSV files from Cronometer.
2. **Data Processing and Visualisation**: Processing the exported data and creating visualisations.
3. **Data Storage**: Uploading the processed data and visualisations to Amazon S3.

## Prerequisites

- **Python**: Ensure Python is installed on your system.
- **Docker**: Docker must be installed and running.
- **AWS CLI**: For configuring AWS credentials.
- **Selenium**: For automating web interactions.
- **WebDriver**: Appropriate WebDriver for your browser (e.g., ChromeDriver for Google Chrome).

## Setup

### 1. Setting Up Airflow

1. Clone the repository:
    ```bash
    git clone https://github.com/JackXLin/Cronometer-ETL-with-Airflow-and-Selenium
    cd <repository-directory>
    ```

2. Create a `requirements.txt` file with the necessary packages:
    - pandas
    - matplotlib
    - selenium
    - boto3

3. Create a `Dockerfile` to extend the Airflow image with the required packages.

4. Update the `docker-compose.yaml` file to use the custom Dockerfile and include additional volumes for CSV storage.

### 2. AWS Credentials Configuration

Configure your AWS credentials using one of the following methods:

#### Method 1: Using AWS CLI
```bash
aws configure
```
## Method 2: Using Environment Variables

Add the following to your `docker-compose.yaml`:

```yaml
environment:
  AWS_ACCESS_KEY_ID: your-access-key-id
  AWS_SECRET_ACCESS_KEY: your-secret-access-key
  AWS_DEFAULT_REGION: your-region
```
### 3. Running the Docker Containers

Build and run the Docker containers:

```bash
docker-compose build
docker-compose up -d
```
DAG Configuration

Create a DAG to automate the entire process. The DAG should include tasks for:

    Fetching the CSV data from Cronometer.
    Processing the CSV data.
    Visualising the processed data.
    Uploading the visualisation to S3.

Automating Cronometer Data Export

    Install Selenium to automate web interactions for exporting data.
    Create an Automation Script to log in to Cronometer, navigate to the export data section, and download the CSV files.

Conclusion

This README.md provides an overview of setting up an automated data pipeline using Apache Airflow to collect, process, visualise, and store data from Cronometer. Follow the steps to configure your environment, set up Airflow, automate data export, and run your data pipeline.

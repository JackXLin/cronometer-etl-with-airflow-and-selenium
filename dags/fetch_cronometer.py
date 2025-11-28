from selenium import webdriver
from selenium.webdriver import FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
import glob
from dotenv import load_dotenv

# Constants for download timeout
DOWNLOAD_TIMEOUT_SECONDS = 300  # 5 minutes
DOWNLOAD_CHECK_INTERVAL_SECONDS = 5  # Check every 5 seconds


def wait_for_file_download(download_dir, filename_pattern, timeout=DOWNLOAD_TIMEOUT_SECONDS):
    """
    Wait for a file matching the pattern to appear in the download directory.

    Args:
        download_dir (str): Directory where files are downloaded.
        filename_pattern (str): Glob pattern to match the file (e.g., '*daily*.csv').
        timeout (int): Maximum time to wait in seconds (default: 300 = 5 minutes).

    Returns:
        str: Path to the downloaded file if found, None otherwise.
    """
    start_time = time.time()
    search_pattern = os.path.join(download_dir, filename_pattern)
    
    print(f"Waiting for file matching '{filename_pattern}' in {download_dir}...")
    print(f"Timeout set to {timeout} seconds ({timeout // 60} minutes)")
    
    while time.time() - start_time < timeout:
        # Check for matching files (excluding partial downloads)
        matching_files = glob.glob(search_pattern)
        # Filter out partial downloads (.part, .crdownload, .tmp files)
        complete_files = [
            f for f in matching_files 
            if not f.endswith(('.part', '.crdownload', '.tmp'))
        ]
        
        if complete_files:
            # Get the most recently modified file
            latest_file = max(complete_files, key=os.path.getmtime)
            elapsed = time.time() - start_time
            print(f"File found: {latest_file} (after {elapsed:.1f} seconds)")
            return latest_file
        
        elapsed = time.time() - start_time
        print(f"Waiting for download... ({elapsed:.0f}/{timeout} seconds)")
        time.sleep(DOWNLOAD_CHECK_INTERVAL_SECONDS)
    
    print(f"Timeout: File not found after {timeout} seconds")
    return None

def select_all_time(driver, wait):
    # Locate the dropdown button using a suitable XPath
    dropdown_button_xpath = "//div[contains(@class, 'select-pretty')]//button"
    dropdown_button = wait.until(EC.element_to_be_clickable((By.XPATH, dropdown_button_xpath)))
    print("Dropdown button found")

    # Ensure the dropdown button is in view
    driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_button)
    time.sleep(1)  # Add a short sleep to ensure scrolling is complete

    # Click the dropdown button
    try:
        dropdown_button.click()
        print("Dropdown button clicked")
    except Exception as e:
        print(f"Failed to click the dropdown button. Exception: {str(e)}")
        driver.save_screenshot('dropdown_button_click_failed.png')
        driver.quit()
        exit()

    # Adding a short sleep to ensure the dropdown options are loaded
    time.sleep(2)

    # Directly set the value using JavaScript
    driver.execute_script("""
        var dropdown = document.querySelector('.select-pretty .dropdown-btn');
        var options = document.querySelectorAll('a.gwt-Anchor.dropdown-item');
        options.forEach(function(option) {
            if (option.textContent.trim() === 'All Time') {
                option.click();
            }
        });
        dropdown.textContent = 'All Time';
    """)

    # Verify the selected option
    time.sleep(2)  # Wait for the option to be set
    selected_option = driver.execute_script("return document.querySelector('.select-pretty .dropdown-btn').textContent.trim();")
    print(f"Selected option: {selected_option}")

    if selected_option != "All Time":
        print("Failed to select 'All Time' option. Exiting.")
        driver.save_screenshot('failed_to_select_all_time.png')
        with open('page_source_failed_selection.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        driver.quit()
        exit()

def cronometer_export():
    load_dotenv()
    username = os.getenv("CRONOMETER_USERNAME")
    password = os.getenv("CRONOMETER_PASSWORD")

    # Setup Firefox options
    options = FirefoxOptions()
    options.add_argument("--headless")

    # Set download directory
    download_dir = "/opt/airflow/csvs"
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.manager.showWhenStarting", False)
    options.set_preference("browser.download.dir", download_dir)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/csv,application/csv,application/octet-stream")

    # Pass the options to the Firefox driver
    driver = webdriver.Firefox(options=options)

    try:
        driver.get("https://www.cronometer.com/login/")

        wait = WebDriverWait(driver, 20)
        email_field = wait.until(EC.visibility_of_element_located((By.ID, "username")))
        password_field = wait.until(EC.visibility_of_element_located((By.ID, "password")))
        submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[span[@id="login_txt"]]')))

        email_field.send_keys(username)
        password_field.send_keys(password)
        submit_button.click()

        # Wait for the sidebar to be present
        sidebar_wrapper = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "sidebar-wrapper")))

        # Now wait for the "More" button to be clickable
        more_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='More']")))

        # Perform actions on the "More" button
        more_button.click()

        # Wait for the "Account" link to be present and click it
        account_link = wait.until(EC.visibility_of_element_located((By.XPATH, "//a[@href='#account']")))
        account_link.click()

        # Wait for the "Export Data" button to be visible
        export_data_button = wait.until(EC.visibility_of_element_located((By.XPATH, "//button[text()='Export Data']")))

        # Scroll the "Export Data" button into view and click it
        driver.execute_script("arguments[0].scrollIntoView(true);", export_data_button)
        driver.execute_script("arguments[0].click();", export_data_button)

        # Wait for the popup to be visible
        popup = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "titlebar-container")))

        # Select "All Time" for the first export
        select_all_time(driver, wait)

        # Scroll the "Export Daily Nutrition" button into view and click it
        export_daily_nutrition_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Export Daily Nutrition")]'))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", export_daily_nutrition_button)
        driver.execute_script("arguments[0].click();", export_daily_nutrition_button)

        # Wait for daily summary CSV to download (up to 5 minutes)
        daily_summary_file = wait_for_file_download(
            download_dir, 
            '*daily*.csv',  # Matches dailysummary.csv or daily-summary.csv
            timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        
        if daily_summary_file is None:
            print("ERROR: Daily summary CSV download failed or timed out!")
            driver.save_screenshot('daily_summary_download_failed.png')
            raise TimeoutError("Daily summary CSV download timed out after 5 minutes")

        # Re-select "All Time" for the second export
        # Scroll the "Export Data" button into view and click it
        driver.execute_script("arguments[0].scrollIntoView(true);", export_data_button)
        driver.execute_script("arguments[0].click();", export_data_button)

        # Wait for the popup to be visible again
        popup = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "titlebar-container")))

        select_all_time(driver, wait)

        # Interact with the "Export Biometrics" button
        export_biometrics_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Export Biometrics")]'))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", export_biometrics_button)
        driver.execute_script("arguments[0].click();", export_biometrics_button)

        # Wait for biometrics CSV to download (up to 5 minutes)
        biometrics_file = wait_for_file_download(
            download_dir,
            '*biometric*.csv',  # Matches biometrics.csv
            timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        
        if biometrics_file is None:
            print("ERROR: Biometrics CSV download failed or timed out!")
            driver.save_screenshot('biometrics_download_failed.png')
            raise TimeoutError("Biometrics CSV download timed out after 5 minutes")

        # Print a confirmation message
        print("Downloaded CSVs successfully!")
    finally:
        driver.quit()

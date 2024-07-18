from selenium import webdriver
from selenium.webdriver import FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
from dotenv import load_dotenv

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
        
        # FIRST CSV FILE DOWNLOAD
        # Interact with the "Export Daily Nutrition" button
        export_daily_nutrition_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Export Daily Nutrition")]'))
        )

        # Scroll the "Export Daily Nutrition" button into view and click it
        driver.execute_script("arguments[0].scrollIntoView(true);", export_daily_nutrition_button)
        driver.execute_script("arguments[0].click();", export_daily_nutrition_button)

        time.sleep(1)

        # SECOND CSV FILE DOWNLOAD
        # Scroll the "Export Data" button into view and click it
        driver.execute_script("arguments[0].scrollIntoView(true);", export_data_button)
        driver.execute_script("arguments[0].click();", export_data_button)

        # Wait for the popup to be visible
        popup = wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "titlebar-container")))

        # Interact with the "Export Biometrics" button
        export_biometrics_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Export Biometrics")]'))
        )

        # Scroll the "Export Biometrics" button into view and click it
        driver.execute_script("arguments[0].scrollIntoView(true);", export_biometrics_button)
        driver.execute_script("arguments[0].click();", export_biometrics_button)

        time.sleep(1)

        # Print a confirmation message
        print("Downloaded CSVs successfully!")
    finally:
        driver.quit()



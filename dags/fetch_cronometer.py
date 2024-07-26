from selenium import webdriver
from selenium.webdriver import FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
from dotenv import load_dotenv

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

        time.sleep(5)

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

        time.sleep(5)

        # Print a confirmation message
        print("Downloaded CSVs successfully!")
    finally:
        driver.quit()

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver import FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
import glob
from typing import Optional
from dotenv import load_dotenv

# Constants for download timeout
DOWNLOAD_TIMEOUT_SECONDS = 300  # 5 minutes
DOWNLOAD_CHECK_INTERVAL_SECONDS = 5  # Check every 5 seconds
DAILY_SUMMARY_OUTPUT_FILENAME = "dailysummary.csv"
BIOMETRICS_OUTPUT_FILENAME = "biometrics.csv"


class CronometerExportError(RuntimeError):
    """Raised when the Cronometer export workflow cannot complete."""


def _get_file_signature(file_path: str) -> tuple[int, int]:
    """Return a stable signature for a downloaded file.

    Args:
        file_path (str): Path to the downloaded file.

    Returns:
        tuple[int, int]: File modification time in nanoseconds and file size.
    """
    file_stat = os.stat(file_path)
    return file_stat.st_mtime_ns, file_stat.st_size


def _list_complete_files(download_dir: str, filename_pattern: str) -> list[str]:
    """List fully downloaded files matching a glob pattern.

    Args:
        download_dir (str): Directory where files are downloaded.
        filename_pattern (str): Glob pattern to match candidate files.

    Returns:
        list[str]: Matching files with temporary browser artifacts removed.
    """
    search_pattern = os.path.join(download_dir, filename_pattern)
    matching_files = glob.glob(search_pattern)
    return [
        file_path
        for file_path in matching_files
        if not file_path.endswith((".part", ".crdownload", ".tmp"))
    ]


def snapshot_matching_files(
    download_dir: str,
    filename_pattern: str,
) -> dict[str, tuple[int, int]]:
    """Capture matching files before triggering a new download.

    Args:
        download_dir (str): Directory where files are downloaded.
        filename_pattern (str): Glob pattern to match candidate files.

    Returns:
        dict[str, tuple[int, int]]: File paths mapped to modification-time and size signatures.
    """
    return {
        file_path: _get_file_signature(file_path)
        for file_path in _list_complete_files(download_dir, filename_pattern)
    }


def wait_for_file_download(
    download_dir: str,
    filename_pattern: str,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    existing_files: Optional[dict[str, tuple[int, int]]] = None,
) -> str:
    """Wait for a new or updated downloaded file to appear.

    Args:
        download_dir (str): Directory where files are downloaded.
        filename_pattern (str): Glob pattern to match the file.
        timeout (int): Maximum time to wait in seconds.
        existing_files (Optional[dict[str, tuple[int, int]]]): Snapshot of matching
            files captured before the export was triggered.

    Returns:
        str: Path to the new or updated file if found.
    """
    start_time = time.time()
    known_files = existing_files or {}

    print(f"Waiting for file matching '{filename_pattern}' in {download_dir}...")
    print(f"Timeout set to {timeout} seconds ({timeout // 60} minutes)")

    while time.time() - start_time < timeout:
        complete_files = _list_complete_files(download_dir, filename_pattern)
        new_or_updated_files = [
            file_path
            for file_path in complete_files
            if file_path not in known_files
            or _get_file_signature(file_path) != known_files[file_path]
        ]

        if new_or_updated_files:
            latest_file = max(new_or_updated_files, key=os.path.getmtime)
            elapsed = time.time() - start_time
            print(f"File found: {latest_file} (after {elapsed:.1f} seconds)")
            return latest_file

        elapsed = time.time() - start_time
        print(f"Waiting for download... ({elapsed:.0f}/{timeout} seconds)")
        time.sleep(DOWNLOAD_CHECK_INTERVAL_SECONDS)

    print(f"Timeout: File not found after {timeout} seconds")
    raise TimeoutError("File download timed out")


def _move_download_to_canonical_path(downloaded_file_path: str, destination_path: str) -> str:
    """Move a downloaded export to the canonical DAG filename.

    Args:
        downloaded_file_path (str): Path to the downloaded export.
        destination_path (str): Canonical output path expected by the DAG.

    Returns:
        str: Canonical output path.
    """
    source_path = os.path.abspath(downloaded_file_path)
    target_path = os.path.abspath(destination_path)
    if source_path == target_path:
        return target_path

    os.replace(source_path, target_path)
    return target_path


def _dismiss_known_overlays(driver: webdriver.Firefox) -> bool:
    """Dismiss or hide known overlays that block Cronometer export clicks.

    Args:
        driver (webdriver.Firefox): Selenium Firefox driver.

    Returns:
        bool: True when a blocking overlay was dismissed or hidden.
    """
    overlay_removed = driver.execute_script(
        """
        const overlaySelectors = [
            '.ncmp__banner-inner',
            '.ncmp__banner',
            '[class*="ncmp__banner"]',
        ];
        const dismissLabels = ['accept', 'agree', 'ok', 'okay', 'close', 'got it', 'dismiss'];
        for (const selector of overlaySelectors) {
            const overlay = document.querySelector(selector);
            if (!overlay) {
                continue;
            }
            const buttons = overlay.querySelectorAll('button, [role="button"], a');
            for (const button of buttons) {
                const label = (button.textContent || '').trim().toLowerCase();
                if (dismissLabels.some((candidate) => label.includes(candidate))) {
                    button.click();
                    return true;
                }
            }
            overlay.style.setProperty('display', 'none', 'important');
            overlay.style.setProperty('visibility', 'hidden', 'important');
            overlay.style.setProperty('pointer-events', 'none', 'important');
            if (overlay.parentElement) {
                overlay.parentElement.style.setProperty('pointer-events', 'none', 'important');
            }
            return true;
        }
        return false;
        """
    )
    return bool(overlay_removed)


def _click_element(
    driver: webdriver.Firefox,
    wait: WebDriverWait,
    locator: tuple[str, str],
    description: str,
) -> None:
    """Click a Cronometer UI element with retries.

    Args:
        driver (webdriver.Firefox): Selenium Firefox driver.
        wait (WebDriverWait): Explicit wait helper.
        locator (tuple[str, str]): Selenium locator for the element.
        description (str): Human-readable element description for logs.

    Returns:
        None

    Raises:
        CronometerExportError: If the element cannot be clicked after retries.
    """
    last_error: Optional[Exception] = None
    artifact_prefix = description.lower().replace(" ", "_")
    for _ in range(3):
        try:
            element = wait.until(EC.element_to_be_clickable(locator))
            print(f"{description} found")
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            try:
                element.click()
            except ElementClickInterceptedException as exc:
                last_error = exc
                overlay_dismissed = _dismiss_known_overlays(driver)
                time.sleep(1)
                element = wait.until(EC.element_to_be_clickable(locator))
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                driver.execute_script("arguments[0].click();", element)
                if overlay_dismissed:
                    print(f"Dismissed blocking overlay before clicking {description}.")
            print(f"{description} clicked")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)

    driver.save_screenshot(f"{artifact_prefix}_click_failed.png")
    raise CronometerExportError(
        f"Failed to click {description} after multiple attempts."
    ) from last_error


def select_all_time(driver: webdriver.Firefox, wait: WebDriverWait) -> None:
    """Select the `All Time` export range in Cronometer.

    Args:
        driver (webdriver.Firefox): Selenium Firefox driver.
        wait (WebDriverWait): Explicit wait helper.

    Returns:
        None

    Raises:
        CronometerExportError: If the export range cannot be set to `All Time`.
    """
    dropdown_button_xpath = "//div[contains(@class, 'select-pretty')]//button"
    _click_element(
        driver,
        wait,
        (By.XPATH, dropdown_button_xpath),
        "Dropdown button",
    )
    time.sleep(2)
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
    time.sleep(2)
    selected_option = driver.execute_script(
        "return document.querySelector('.select-pretty .dropdown-btn').textContent.trim();"
    )
    print(f"Selected option: {selected_option}")

    if selected_option != "All Time":
        driver.save_screenshot("failed_to_select_all_time.png")
        with open("page_source_failed_selection.html", "w", encoding="utf-8") as page_source_file:
            page_source_file.write(driver.page_source)
        raise CronometerExportError(
            "Failed to select `All Time` in the Cronometer export dialog."
        )


def _open_export_data_modal(driver: webdriver.Firefox, wait: WebDriverWait) -> None:
    """Open the Cronometer export modal.

    Args:
        driver (webdriver.Firefox): Selenium Firefox driver.
        wait (WebDriverWait): Explicit wait helper.

    Returns:
        None
    """
    _click_element(
        driver,
        wait,
        (By.XPATH, "//button[text()='Export Data']"),
        "Export Data button",
    )
    wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "titlebar-container")))


def cronometer_export() -> None:
    """Export Cronometer daily nutrition and biometrics CSVs.

    Args:
        None

    Returns:
        None

    Raises:
        TimeoutError: If either Cronometer export does not download in time.
        CronometerExportError: If the Selenium workflow cannot complete.
        FileNotFoundError: If canonical output files are missing after export.
    """
    load_dotenv()
    username = os.getenv("CRONOMETER_USERNAME")
    password = os.getenv("CRONOMETER_PASSWORD")

    options = FirefoxOptions()
    options.add_argument("--headless")

    download_dir = "/opt/airflow/csvs"
    daily_summary_output_path = os.path.join(download_dir, DAILY_SUMMARY_OUTPUT_FILENAME)
    biometrics_output_path = os.path.join(download_dir, BIOMETRICS_OUTPUT_FILENAME)
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.manager.showWhenStarting", False)
    options.set_preference("browser.download.dir", download_dir)
    options.set_preference(
        "browser.helperApps.neverAsk.saveToDisk",
        "text/csv,application/csv,application/octet-stream",
    )

    driver = webdriver.Firefox(options=options)

    try:
        driver.get("https://www.cronometer.com/login/")

        wait = WebDriverWait(driver, 20)
        email_field = wait.until(EC.visibility_of_element_located((By.ID, "username")))
        password_field = wait.until(EC.visibility_of_element_located((By.ID, "password")))
        submit_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//button[span[@id="login_txt"]]'))
        )

        email_field.send_keys(username)
        password_field.send_keys(password)
        submit_button.click()

        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "sidebar-wrapper")))
        _click_element(driver, wait, (By.XPATH, "//span[text()='More']"), "More button")
        _click_element(driver, wait, (By.XPATH, "//a[@href='#account']"), "Account link")

        _open_export_data_modal(driver, wait)
        select_all_time(driver, wait)

        existing_daily_files = snapshot_matching_files(download_dir, "*daily*.csv")
        _click_element(
            driver,
            wait,
            (By.XPATH, '//button[contains(text(), "Export Daily Nutrition")]'),
            "Export Daily Nutrition button",
        )
        daily_summary_file = wait_for_file_download(
            download_dir,
            "*daily*.csv",
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            existing_files=existing_daily_files,
        )
        daily_summary_file = _move_download_to_canonical_path(
            daily_summary_file,
            daily_summary_output_path,
        )

        _open_export_data_modal(driver, wait)
        select_all_time(driver, wait)

        existing_biometrics_files = snapshot_matching_files(download_dir, "*biometric*.csv")
        _click_element(
            driver,
            wait,
            (By.XPATH, '//button[contains(text(), "Export Biometrics")]'),
            "Export Biometrics button",
        )
        biometrics_file = wait_for_file_download(
            download_dir,
            "*biometric*.csv",
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            existing_files=existing_biometrics_files,
        )
        biometrics_file = _move_download_to_canonical_path(
            biometrics_file,
            biometrics_output_path,
        )

        if not os.path.exists(daily_summary_file):
            raise FileNotFoundError(
                f"Daily summary CSV not found at `{daily_summary_file}` after export."
            )
        if not os.path.exists(biometrics_file):
            raise FileNotFoundError(
                f"Biometrics CSV not found at `{biometrics_file}` after export."
            )

        print(
            "Downloaded Cronometer CSVs successfully to "
            f"{daily_summary_file} and {biometrics_file}!"
        )
    finally:
        driver.quit()

"""Tests for the Cronometer export helpers."""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import fetch_cronometer


class _FakeWait:
    """Minimal wait helper returning placeholder Selenium elements."""

    def __init__(self, result=None) -> None:
        """Initialize the fake wait helper.

        Args:
            result (object): Element or value returned from `until`.

        Returns:
            None
        """
        self.result = result if result is not None else object()

    def until(self, _condition):
        """Return a placeholder element for selector waits.

        Args:
            _condition (object): Ignored expected condition.

        Returns:
            object: Placeholder element.
        """
        return self.result


class _FakeElement:
    """Minimal Selenium element stub for click helper tests."""

    def __init__(self, intercepted_clicks: int = 0) -> None:
        """Initialize the fake element.

        Args:
            intercepted_clicks (int): Number of intercepted clicks before success.

        Returns:
            None
        """
        self.intercepted_clicks = intercepted_clicks
        self.click_count = 0

    def click(self) -> None:
        """Simulate Selenium click interception before eventual success.

        Returns:
            None

        Raises:
            ElementClickInterceptedException: When configured to block the click.
        """
        self.click_count += 1
        if self.click_count <= self.intercepted_clicks:
            raise fetch_cronometer.ElementClickInterceptedException("blocked")


class _FakeDriver:
    """Minimal Selenium driver stub for error-path tests."""

    def __init__(self, selected_option: str = "Custom") -> None:
        """Initialize the fake driver.

        Args:
            selected_option (str): Value returned for selected export range.

        Returns:
            None
        """
        self.selected_option = selected_option
        self.page_source = "<html></html>"
        self.screenshots: list[str] = []
        self.executed_scripts: list[str] = []

    def execute_script(self, script: str, *_args):
        """Return the mocked dropdown selection when queried.

        Args:
            script (str): JavaScript snippet.

        Returns:
            object: Mocked script result.
        """
        self.executed_scripts.append(script)
        if "textContent.trim" in script:
            return self.selected_option
        return None

    def save_screenshot(self, path: str) -> None:
        """Record screenshot paths for assertions.

        Args:
            path (str): Screenshot path.

        Returns:
            None
        """
        self.screenshots.append(path)


class TestWaitForFileDownload:
    """Tests for Cronometer download detection."""

    def test_expected_use_detects_only_new_download(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should ignore existing matches and return only the new export file.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        garmin_daily = tmp_path / "garmin_daily.csv"
        garmin_daily.write_text("existing", encoding="utf-8")
        existing_files = fetch_cronometer.snapshot_matching_files(
            str(tmp_path),
            "*daily*.csv",
        )

        monkeypatch.setattr(fetch_cronometer, "DOWNLOAD_CHECK_INTERVAL_SECONDS", 0)

        new_daily = tmp_path / "daily-nutrition-export.csv"

        def create_download() -> None:
            time.sleep(0.01)
            new_daily.write_text("fresh", encoding="utf-8")

        writer_thread = threading.Thread(target=create_download)
        writer_thread.start()
        try:
            result = fetch_cronometer.wait_for_file_download(
                str(tmp_path),
                "*daily*.csv",
                timeout=1,
                existing_files=existing_files,
            )
        finally:
            writer_thread.join()

        assert result == str(new_daily)

    def test_edge_case_detects_updated_existing_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should detect when an existing matching file is updated in place.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        daily_file = tmp_path / "daily-export.csv"
        daily_file.write_text("old", encoding="utf-8")
        existing_files = fetch_cronometer.snapshot_matching_files(
            str(tmp_path),
            "*daily*.csv",
        )

        monkeypatch.setattr(fetch_cronometer, "DOWNLOAD_CHECK_INTERVAL_SECONDS", 0)

        def update_download() -> None:
            time.sleep(0.01)
            daily_file.write_text("new-content", encoding="utf-8")

        writer_thread = threading.Thread(target=update_download)
        writer_thread.start()
        try:
            result = fetch_cronometer.wait_for_file_download(
                str(tmp_path),
                "*daily*.csv",
                timeout=1,
                existing_files=existing_files,
            )
        finally:
            writer_thread.join()

        assert result == str(daily_file)

    def test_failure_case_times_out_when_no_new_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should raise when no new matching download appears.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        existing_daily = tmp_path / "garmin_daily.csv"
        existing_daily.write_text("existing", encoding="utf-8")
        existing_files = fetch_cronometer.snapshot_matching_files(
            str(tmp_path),
            "*daily*.csv",
        )

        monkeypatch.setattr(fetch_cronometer, "DOWNLOAD_CHECK_INTERVAL_SECONDS", 0)

        with pytest.raises(TimeoutError):
            fetch_cronometer.wait_for_file_download(
                str(tmp_path),
                "*daily*.csv",
                timeout=0,
                existing_files=existing_files,
            )


class TestCronometerExportHelpers:
    """Tests for Cronometer export helper utilities."""

    def test_expected_use_moves_download_to_canonical_path(self, tmp_path: Path) -> None:
        """Should rename downloaded exports to the DAG's canonical filename.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        source_path = tmp_path / "daily-export-2026-03-20.csv"
        destination_path = tmp_path / "dailysummary.csv"
        source_path.write_text("csv-data", encoding="utf-8")

        result = fetch_cronometer._move_download_to_canonical_path(
            str(source_path),
            str(destination_path),
        )

        assert result == str(destination_path)
        assert destination_path.read_text(encoding="utf-8") == "csv-data"
        assert not source_path.exists()

    def test_failure_case_select_all_time_raises_when_selection_does_not_stick(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should raise a Cronometer export error when the range stays incorrect.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        driver = _FakeDriver(selected_option="Last 30 Days")
        wait = _FakeWait()

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(fetch_cronometer, "_click_element", lambda *_args, **_kwargs: None)

        with pytest.raises(fetch_cronometer.CronometerExportError):
            fetch_cronometer.select_all_time(driver, wait)

        assert "failed_to_select_all_time.png" in driver.screenshots
        assert (tmp_path / "page_source_failed_selection.html").exists()

    def test_edge_case_click_element_dismisses_overlay_after_intercept(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should dismiss overlays and retry with JavaScript when a click is intercepted.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.

        Returns:
            None
        """
        driver = _FakeDriver()
        element = _FakeElement(intercepted_clicks=1)
        wait = _FakeWait(result=element)

        monkeypatch.setattr(fetch_cronometer.time, "sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(fetch_cronometer, "_dismiss_known_overlays", lambda *_args, **_kwargs: True)

        fetch_cronometer._click_element(
            driver,
            wait,
            ("xpath", "//button[text()='Export Data']"),
            "Export Data button",
        )

        assert element.click_count == 1
        assert any("arguments[0].click();" in script for script in driver.executed_scripts)

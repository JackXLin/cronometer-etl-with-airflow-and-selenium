"""Tests for Garmin historical export import."""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import garmin_export_import


class TestBuildGarminHistoricalArtifacts:
    """Tests for Garmin export import into mounted-volume artifacts."""

    def test_expected_use_builds_daily_activity_and_empty_heart_rate_artifacts(
        self,
        tmp_path: Path,
    ) -> None:
        """Should build Garmin daily and activity artifacts from exported JSON files.

        Args:
            tmp_path (Path): Temporary workspace.

        Returns:
            None
        """
        export_root = tmp_path / "garmin_data"
        aggregator_dir = export_root / "DI-Connect-Aggregator"
        fitness_dir = export_root / "DI-Connect-Fitness"
        wellness_dir = export_root / "DI-Connect-Wellness"
        aggregator_dir.mkdir(parents=True)
        fitness_dir.mkdir(parents=True)
        wellness_dir.mkdir(parents=True)

        (aggregator_dir / "UDSFile_2024-04-20_2024-07-29.json").write_text(
            json.dumps(
                [
                    {
                        "calendarDate": "2024-05-03",
                        "totalSteps": 8915,
                        "totalDistanceMeters": 7260,
                        "activeKilocalories": 742,
                        "moderateIntensityMinutes": 91,
                        "vigorousIntensityMinutes": 1,
                        "restingHeartRate": 60,
                        "minHeartRate": 55,
                        "maxHeartRate": 124,
                        "averageSpo2Value": 96,
                        "allDayStress": {
                            "aggregatorList": [
                                {
                                    "type": "TOTAL",
                                    "averageStressLevel": 14,
                                }
                            ]
                        },
                        "bodyBattery": {
                            "bodyBatteryStatList": [
                                {
                                    "bodyBatteryStatType": "HIGHEST",
                                    "statsValue": 74,
                                },
                                {
                                    "bodyBatteryStatType": "LOWEST",
                                    "statsValue": 18,
                                },
                            ]
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )
        (wellness_dir / "2024-04-21_2024-07-30_122108862_sleepData.json").write_text(
            json.dumps(
                [
                    {
                        "calendarDate": "2024-05-03",
                        "deepSleepSeconds": 3600,
                        "lightSleepSeconds": 14400,
                        "remSleepSeconds": 7200,
                        "averageRespiration": 15,
                        "sleepScores": {"overallScore": 86},
                        "spo2SleepSummary": {"averageSPO2": 95},
                    }
                ]
            ),
            encoding="utf-8",
        )
        (wellness_dir / "122108862_fitnessAgeData.json").write_text(
            json.dumps(
                [
                    {
                        "asOfDateGmt": "2024-05-03T00:00:00.0",
                        "rhr": 59,
                    }
                ]
            ),
            encoding="utf-8",
        )
        (wellness_dir / "2025-12-10_2026-03-20_122108862_healthStatusData.json").write_text(
            json.dumps(
                [
                    {
                        "calendarDate": "2024-05-03",
                        "metrics": [
                            {"type": "HRV", "value": 62},
                            {"type": "HR", "value": 57},
                            {"type": "SPO2", "value": 97},
                            {"type": "RESPIRATION", "value": 14},
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        (wellness_dir / "122108862_wellnessActivities.json").write_text(
            json.dumps(
                [
                    {
                        "calendarDate": "2024-05-03",
                        "summaryTypeDataList": [
                            {"summaryType": "HEART_RATE", "minValue": 60, "maxValue": 72, "avgValue": 64},
                            {"summaryType": "RESPIRATION", "avgValue": 13.8},
                            {"summaryType": "STRESS", "avgValue": 5},
                            {"summaryType": "SPO2", "avgValue": 97},
                            {"summaryType": "RMSSD_HRV", "avgValue": 56},
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        (fitness_dir / "jack.llll_apps@yahoo.com_1001_summarizedActivities.json").write_text(
            json.dumps(
                [
                    {
                        "summarizedActivitiesExport": [
                            {
                                "activityId": 17290383425,
                                "name": "Strength",
                                "activityType": "strength_training",
                                "startTimeGmt": 1714730400000,
                                "startTimeLocal": 1714734000000,
                                "duration": 3600000,
                                "distance": 0,
                                "avgHr": 107,
                                "maxHr": 149,
                                "calories": 500,
                            }
                        ]
                    }
                ]
            ),
            encoding="utf-8",
        )

        output_path = tmp_path / "garmin_daily.csv"
        result = garmin_export_import.build_garmin_historical_artifacts(
            export_root=export_root,
            output_path=str(output_path),
            merge_existing=False,
        )

        activities_path = output_path.with_name("garmin_activities.csv")
        heart_rate_path = output_path.with_name("garmin_heart_rate_detail.csv")
        daily = pd.read_csv(result)
        activities = pd.read_csv(activities_path)
        heart_rate = pd.read_csv(heart_rate_path)

        assert result == str(output_path)
        assert list(daily["Date"]) == ["2024-05-03"]
        assert daily.loc[0, "garmin_steps"] == 8915
        assert daily.loc[0, "garmin_sleep_seconds"] == 25200
        assert daily.loc[0, "garmin_sleep_score"] == 86
        assert daily.loc[0, "garmin_avg_stress"] == 14
        assert daily.loc[0, "garmin_body_battery_max"] == 74
        assert daily.loc[0, "garmin_body_battery_min"] == 18
        assert daily.loc[0, "garmin_hrv"] == 62
        assert daily.loc[0, "garmin_respiration_avg"] == 14
        assert daily.loc[0, "garmin_spo2_avg"] == 97
        assert daily.loc[0, "garmin_activity_count"] == 1
        assert daily.loc[0, "garmin_activity_duration_min"] == 60
        assert daily.loc[0, "garmin_activity_calories_from_sessions_kcal"] == 500
        assert activities.loc[0, "garmin_activity_name"] == "Strength"
        assert activities.loc[0, "garmin_activity_type"] == "strength_training"
        assert list(heart_rate.columns) == garmin_export_import.GARMIN_HEART_RATE_DETAIL_COLUMNS
        assert heart_rate.empty

    def test_edge_case_merge_existing_keeps_non_overlapping_history(
        self,
        tmp_path: Path,
    ) -> None:
        """Should merge imported export history with existing Garmin artifacts.

        Args:
            tmp_path (Path): Temporary workspace.

        Returns:
            None
        """
        export_root = tmp_path / "garmin_data"
        aggregator_dir = export_root / "DI-Connect-Aggregator"
        fitness_dir = export_root / "DI-Connect-Fitness"
        aggregator_dir.mkdir(parents=True)
        fitness_dir.mkdir(parents=True)

        (aggregator_dir / "UDSFile_2024-04-20_2024-07-29.json").write_text(
            json.dumps(
                [
                    {
                        "calendarDate": "2024-05-03",
                        "totalSteps": 4000,
                    }
                ]
            ),
            encoding="utf-8",
        )
        (fitness_dir / "jack.llll_apps@yahoo.com_1001_summarizedActivities.json").write_text(
            json.dumps([{"summarizedActivitiesExport": []}]),
            encoding="utf-8",
        )

        output_path = tmp_path / "garmin_daily.csv"
        pd.DataFrame(
            {
                "Date": ["2024-05-02"],
                "garmin_steps": [3000],
            }
        ).to_csv(output_path, index=False)
        pd.DataFrame(columns=garmin_export_import.GARMIN_ACTIVITY_COLUMNS).to_csv(
            output_path.with_name("garmin_activities.csv"),
            index=False,
        )
        pd.DataFrame(columns=garmin_export_import.GARMIN_HEART_RATE_DETAIL_COLUMNS).to_csv(
            output_path.with_name("garmin_heart_rate_detail.csv"),
            index=False,
        )

        garmin_export_import.build_garmin_historical_artifacts(
            export_root=export_root,
            output_path=str(output_path),
            merge_existing=True,
        )

        daily = pd.read_csv(output_path)
        assert list(daily["Date"]) == ["2024-05-02", "2024-05-03"]
        assert list(daily["garmin_steps"])[:2] == [3000.0, 4000.0]

    def test_failure_case_missing_export_root_raises(self, tmp_path: Path) -> None:
        """Should fail clearly when the Garmin export root is missing.

        Args:
            tmp_path (Path): Temporary workspace.

        Returns:
            None
        """
        missing_root = tmp_path / "missing_garmin_data"

        with pytest.raises(FileNotFoundError):
            garmin_export_import.build_garmin_historical_artifacts(
                export_root=missing_root,
                output_path=str(tmp_path / "garmin_daily.csv"),
            )

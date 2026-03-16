"""Helpers for Garmin daily payload normalization."""

import logging
from typing import Any, Iterable, List, Optional, Sequence

from garmin_client import (
    GarthHTTPError,
    GarminBootstrapRequiredError,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminRateLimitError,
    GarminServiceError,
)


LOGGER = logging.getLogger(__name__)


def _extract_nested_value(
    payload: Any,
    candidate_paths: Iterable[Sequence[str]],
) -> Optional[Any]:
    """Extract the first non-null value found across candidate nested paths.

    Args:
        payload (Any): Nested Garmin payload.
        candidate_paths (Iterable[Sequence[str]]): Candidate key paths.

    Returns:
        Any | None: The first resolved value, if present.
    """
    for path in candidate_paths:
        current_value = payload
        for key in path:
            if isinstance(current_value, dict) and key in current_value:
                current_value = current_value[key]
                continue
            current_value = None
            break
        if current_value is not None:
            return current_value
    return None


def _extract_duration_minutes(
    payload: Any,
    minute_paths: Iterable[Sequence[str]],
    second_paths: Iterable[Sequence[str]],
) -> Optional[float]:
    """Resolve a Garmin duration field as minutes.

    Args:
        payload (Any): Garmin payload containing duration values.
        minute_paths (Iterable[Sequence[str]]): Candidate minute-valued paths.
        second_paths (Iterable[Sequence[str]]): Candidate second-valued paths.

    Returns:
        float | None: Duration in minutes, if available.
    """
    minutes_value = _extract_nested_value(payload, minute_paths)
    if minutes_value is not None:
        return float(minutes_value)

    seconds_value = _extract_nested_value(payload, second_paths)
    if seconds_value is not None:
        return float(seconds_value) / 60.0
    return None


def _call_optional_api_method(
    client: Any,
    method_names: Iterable[str],
    date_str: str,
) -> Optional[Any]:
    """Call the first available Garmin method for a date-sensitive endpoint.

    Args:
        client (Any): Authenticated Garmin client.
        method_names (Iterable[str]): Candidate client method names.
        date_str (str): ISO date string passed to the Garmin endpoint.

    Returns:
        Any | None: Endpoint payload or None if no compatible method exists.

    Raises:
        GarminBootstrapRequiredError: If the session is no longer authenticated.
        GarminRateLimitError: If Garmin rate limits API access.
        GarminServiceError: If Garmin cannot satisfy the request.
    """
    return _call_optional_api_method_variants(
        client=client,
        method_names=method_names,
        call_variants=((date_str,),),
        date_str=date_str,
    )


def _call_optional_api_method_variants(
    client: Any,
    method_names: Iterable[str],
    call_variants: Iterable[Sequence[str]],
    date_str: str,
) -> Optional[Any]:
    """Call the first compatible Garmin method across multiple signatures.

    Args:
        client (Any): Authenticated Garmin client.
        method_names (Iterable[str]): Candidate client method names.
        call_variants (Iterable[Sequence[str]]): Supported positional arguments.
        date_str (str): ISO date string used for logging and error messages.

    Returns:
        Any | None: Endpoint payload or None if no compatible method exists.

    Raises:
        GarminBootstrapRequiredError: If the session is no longer authenticated.
        GarminRateLimitError: If Garmin rate limits API access.
        GarminServiceError: If Garmin cannot satisfy the request.
    """
    for method_name in method_names:
        method = getattr(client, method_name, None)
        if not callable(method):
            continue

        signature_error: Optional[TypeError] = None
        for call_args in call_variants:
            try:
                return method(*call_args)
            except TypeError as exc:
                signature_error = exc
                continue
            except GarminConnectTooManyRequestsError as exc:
                raise GarminRateLimitError(
                    f"Garmin rate-limited the `{method_name}` request for {date_str}."
                ) from exc
            except GarminConnectAuthenticationError as exc:
                raise GarminBootstrapRequiredError(
                    "Garmin authentication expired during data extraction. Run the manual "
                    "bootstrap flow again before retrying."
                ) from exc
            except GarminConnectConnectionError as exc:
                raise GarminServiceError(
                    f"Garmin Connect was unavailable while calling `{method_name}` for {date_str}."
                ) from exc
            except GarthHTTPError as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                error_text = str(exc)
                if status_code == 429 or "429" in error_text:
                    raise GarminRateLimitError(
                        f"Garmin rate-limited the `{method_name}` request for {date_str}."
                    ) from exc
                if status_code in (401, 403) or "401" in error_text or "403" in error_text:
                    raise GarminBootstrapRequiredError(
                        "Garmin authentication expired during data extraction. Run the manual "
                        "bootstrap flow again before retrying."
                    ) from exc
                if status_code in (400, 404) or "400" in error_text or "404" in error_text:
                    LOGGER.debug(
                        "Garmin endpoint `%s` is unavailable for %s: %s",
                        method_name,
                        date_str,
                        exc,
                    )
                    return None
                raise GarminServiceError(
                    f"Garmin returned an unexpected HTTP response while calling `{method_name}` "
                    f"for {date_str}."
                ) from exc

        if signature_error is not None:
            LOGGER.debug(
                "Garmin endpoint `%s` rejected supported call variants for %s: %s",
                method_name,
                date_str,
                signature_error,
            )
    return None


def _extract_numeric_values(payload: Any, candidate_keys: Iterable[str]) -> List[float]:
    """Collect numeric values from nested payloads for matching keys only.

    Args:
        payload (Any): Nested Garmin payload.
        candidate_keys (Iterable[str]): Keys whose numeric values should be collected.

    Returns:
        list[float]: Extracted numeric values.
    """
    matched_keys = set(candidate_keys)
    values: List[float] = []

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in matched_keys and isinstance(value, (int, float)):
                values.append(float(value))
            else:
                values.extend(_extract_numeric_values(value, matched_keys))
        return values

    if isinstance(payload, list):
        for value in payload:
            values.extend(_extract_numeric_values(value, matched_keys))
    return values


def _extract_body_battery_bounds(payload: Any) -> tuple[Optional[float], Optional[float]]:
    """Extract daily body battery max/min from a Garmin body battery payload.

    Args:
        payload (Any): Garmin body battery payload.

    Returns:
        tuple[Optional[float], Optional[float]]: Daily max and min body battery.
    """
    max_value = _extract_nested_value(
        payload,
        [
            ("bodyBatteryMax",),
            ("maxBodyBattery",),
            ("summary", "bodyBatteryMax"),
            ("summary", "maxBodyBattery"),
        ],
    )
    min_value = _extract_nested_value(
        payload,
        [
            ("bodyBatteryMin",),
            ("minBodyBattery",),
            ("summary", "bodyBatteryMin"),
            ("summary", "minBodyBattery"),
        ],
    )

    numeric_samples = [
        value
        for value in _extract_numeric_values(
            payload,
            {
                "bodyBattery",
                "bodyBatteryLevel",
                "charged",
                "chargedBodyBattery",
                "value",
            },
        )
        if 0 <= value <= 100
    ]
    if max_value is None and numeric_samples:
        max_value = max(numeric_samples)
    if min_value is None and numeric_samples:
        min_value = min(numeric_samples)
    return (
        float(max_value) if max_value is not None else None,
        float(min_value) if min_value is not None else None,
    )


def _extract_activity_count(summary_payload: Any, activity_payload: Any) -> Optional[int]:
    """Extract a daily activity count from summary or activity-list payloads.

    Args:
        summary_payload (Any): Garmin daily summary payload.
        activity_payload (Any): Garmin activity-list payload.

    Returns:
        Optional[int]: Number of daily activities when available.
    """
    summary_count = _extract_nested_value(
        summary_payload,
        [
            ("activityCount",),
            ("summary", "activityCount"),
            ("totalActivities",),
        ],
    )
    if summary_count is not None:
        return int(summary_count)

    if isinstance(activity_payload, list):
        return len(activity_payload)

    activity_list = _extract_nested_value(
        activity_payload,
        [
            ("activities",),
            ("activityList",),
            ("items",),
            ("data",),
        ],
    )
    if isinstance(activity_list, list):
        return len(activity_list)

    total_count = _extract_nested_value(
        activity_payload,
        [
            ("total",),
            ("count",),
            ("paging", "totalResults"),
            ("page", "totalElements"),
        ],
    )
    return int(total_count) if total_count is not None else None

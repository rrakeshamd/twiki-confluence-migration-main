"""
Shared utility functions for the TWiki-to-Confluence migration tool.
"""
import os
import subprocess
import requests

# HTTP status codes considered successful
SUCCESS_CODES = frozenset({200, 201, 202, 204})


def is_success_response(status_code: int) -> bool:
    """Return True if the HTTP status code indicates success."""
    return status_code in SUCCESS_CODES


def fetch_webpage(url, username, password, timeout=30):
    """
    Fetch a webpage with basic authentication.

    Args:
        url (str): URL to fetch
        username (str): Authentication username
        password (str): Authentication password
        timeout (int): Request timeout in seconds

    Returns:
        bytes: Raw content of the response, or None on failure
    """
    try:
        response = requests.get(url, auth=(username, password), timeout=timeout)
        if response and response.status_code in SUCCESS_CODES:
            return response.content
    except requests.HTTPError as e:
        print(f"\nHTTPError: {e.response.status_code} - {e.response.reason}")
    except requests.RequestException as e:
        print(f"\nRequestException: {e}")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    return None


def exponential_backoff(attempt, base_delay=5, max_delay=120):
    """
    Return the wait time (seconds) for a given retry attempt using exponential backoff.

    Args:
        attempt (int): Zero-based attempt number
        base_delay (int): Starting delay in seconds
        max_delay (int): Maximum delay cap in seconds

    Returns:
        float: Seconds to wait before the next retry
    """
    return min(base_delay * (2 ** attempt), max_delay)


def clear_screen():
    """Clear the terminal screen in a portable way."""
    subprocess.run(
        ['cls' if os.name == 'nt' else 'clear'],
        shell=(os.name == 'nt'),
        check=False,
    )

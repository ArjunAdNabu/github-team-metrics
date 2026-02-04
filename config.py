"""Configuration management for GitHub Team Metrics project."""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Required fields
    github_token: str
    github_org: str
    google_credentials_path: str
    google_sheet_id: str

    # Optional fields with defaults
    google_sheet_name: str = 'Sheet1'
    user_mapping_file: str = './user_mapping.json'
    days_back: int = 30
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    output_dir: str = './output'
    output_filename: Optional[str] = None
    max_workers: int = 5
    request_timeout: int = 30
    rate_limit_buffer: int = 100


def load_config() -> Config:
    """
    Load and validate configuration from environment variables.

    Returns:
        Config: Configuration object with all settings

    Raises:
        ValueError: If required fields are missing
        FileNotFoundError: If credentials file doesn't exist
    """
    # Required fields
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        raise ValueError(
            "GITHUB_TOKEN is required. Please set it in .env file.\n"
            "Create a token at: https://github.com/settings/tokens"
        )

    google_sheet_id = os.getenv('GOOGLE_SHEET_ID')
    if not google_sheet_id:
        raise ValueError(
            "GOOGLE_SHEET_ID is required. Please set it in .env file.\n"
            "Get the ID from your Google Sheet URL"
        )

    # Validate credentials file
    credentials_path = os.getenv(
        'GOOGLE_CREDENTIALS_PATH',
        './credentials/google_service_account.json'
    )

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Google credentials not found at: {credentials_path}\n"
            f"Download service account JSON from Google Cloud Console"
        )

    # Optional fields with defaults
    github_org = os.getenv('GITHUB_ORG', 'AdNabu-Team')
    google_sheet_name = os.getenv('GOOGLE_SHEET_NAME', 'Sheet1')
    user_mapping_file = os.getenv('USER_MAPPING_FILE', './user_mapping.json')
    days_back = int(os.getenv('DAYS_BACK', '30'))
    start_date = os.getenv('START_DATE')
    end_date = os.getenv('END_DATE')
    output_dir = os.getenv('OUTPUT_DIR', './output')
    output_filename = os.getenv('OUTPUT_FILENAME')
    max_workers = int(os.getenv('MAX_WORKERS', '5'))
    request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
    rate_limit_buffer = int(os.getenv('RATE_LIMIT_BUFFER', '100'))

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    return Config(
        github_token=github_token,
        github_org=github_org,
        google_credentials_path=credentials_path,
        google_sheet_id=google_sheet_id,
        google_sheet_name=google_sheet_name,
        user_mapping_file=user_mapping_file,
        days_back=days_back,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        output_filename=output_filename,
        max_workers=max_workers,
        request_timeout=request_timeout,
        rate_limit_buffer=rate_limit_buffer
    )


def validate_config(config: Config) -> None:
    """
    Validate configuration values.

    Args:
        config: Configuration object to validate

    Raises:
        ValueError: If configuration is invalid
    """
    # Validate days_back
    if config.days_back <= 0:
        raise ValueError(f"DAYS_BACK must be positive, got: {config.days_back}")

    # Validate date range if provided
    if config.start_date and config.end_date:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(config.start_date)
            end = datetime.fromisoformat(config.end_date)
            if start >= end:
                raise ValueError(
                    f"START_DATE must be before END_DATE: {config.start_date} >= {config.end_date}"
                )
        except ValueError as e:
            raise ValueError(f"Invalid date format (use YYYY-MM-DD): {e}")

    # Validate max_workers
    if config.max_workers <= 0:
        raise ValueError(f"MAX_WORKERS must be positive, got: {config.max_workers}")

    # Validate timeout
    if config.request_timeout <= 0:
        raise ValueError(f"REQUEST_TIMEOUT must be positive, got: {config.request_timeout}")


def load_user_mapping(mapping_file: str) -> dict:
    """
    Load user mapping from JSON file.

    Args:
        mapping_file: Path to user mapping JSON file

    Returns:
        Dictionary mapping Sheet names to GitHub usernames
    """
    import json

    if not os.path.exists(mapping_file):
        # Return empty dict if file doesn't exist (optional feature)
        return {}

    try:
        with open(mapping_file, 'r') as f:
            data = json.load(f)

        # Filter out comments (keys starting with _)
        mapping = {k: v for k, v in data.items() if not k.startswith('_')}

        return mapping
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in user mapping file: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load user mapping: {e}")

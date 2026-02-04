"""Google Sheets API client for reading ticket data."""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .utils import calculate_hours_between, retry_with_exponential_backoff


logger = logging.getLogger('github_metrics')


class GoogleSheetsClient:
    """Google Sheets API client using service account authentication."""

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    def __init__(self, credentials_path: str):
        """
        Initialize Google Sheets client.

        Args:
            credentials_path: Path to service account JSON file

        Raises:
            FileNotFoundError: If credentials file doesn't exist
        """
        self.credentials_path = credentials_path

        try:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=credentials)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Google Sheets client: {e}")

    @retry_with_exponential_backoff(
        max_retries=3,
        base_delay=1.0,
        exceptions=(HttpError,)
    )
    def read_sheet(self, sheet_id: str, sheet_name: str = 'Sheet1') -> Dict:
        """
        Read all data from a Google Sheet.

        Args:
            sheet_id: Google Sheet ID (from URL)
            sheet_name: Worksheet name (default: Sheet1)

        Returns:
            Dictionary with headers, rows, and metadata

        Raises:
            HttpError: If sheet access fails
        """
        try:
            # Read entire sheet
            range_name = f"{sheet_name}!A:Z"  # Read columns A-Z

            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()

            rows = result.get('values', [])

            if not rows:
                logger.warning(f"Sheet '{sheet_name}' is empty")
                return {
                    'headers': [],
                    'rows': [],
                    'metadata': {
                        'total_rows': 0,
                        'total_cols': 0,
                        'sheet_name': sheet_name
                    }
                }

            # First row is headers
            headers = rows[0] if rows else []
            data_rows = rows[1:] if len(rows) > 1 else []

            logger.info(f"Read {len(data_rows)} rows from sheet '{sheet_name}'")

            return {
                'headers': headers,
                'rows': data_rows,
                'metadata': {
                    'total_rows': len(data_rows),
                    'total_cols': len(headers),
                    'sheet_name': sheet_name
                }
            }

        except HttpError as e:
            if e.resp.status == 404:
                raise RuntimeError(f"Sheet not found: {sheet_id}. Check the sheet ID.")
            elif e.resp.status == 403:
                raise RuntimeError(
                    f"Permission denied for sheet {sheet_id}. "
                    f"Share the sheet with the service account email."
                )
            else:
                raise


class SheetsDataProcessor:
    """Process and normalize Google Sheets data."""

    # Expected column names from "Tickets and queries.xlsx"
    EXPECTED_COLUMNS = {
        'title': 'Title',
        'priority': 'Priority',
        'type': 'Type',
        'assigned': 'Assigned',
        'reported_by': 'Reported by',
        'reported_time': 'Reported time (M/D/Y T(24))',
        'first_response_time': 'First response time (M/D/Y T(24))',
        'closed_time': 'Closed time (M/D/Y T(24))',
        'duration': 'Duration',
        'bucket': 'Bucket',
        'github_issue': 'GitHub Issue',
        'notes': 'Notes',
        'root_cause_status': 'Root cause status'
    }

    def __init__(self):
        """Initialize sheets data processor."""
        self.column_mapping = {}

    def normalize_data(self, raw_data: Dict) -> List[Dict]:
        """
        Normalize sheet data to list of dictionaries.

        Args:
            raw_data: Raw data from read_sheet()

        Returns:
            List of dictionaries (one per ticket)
        """
        headers = raw_data.get('headers', [])
        rows = raw_data.get('rows', [])

        if not headers or not rows:
            logger.warning("No data to normalize")
            return []

        # Create column mapping (case-insensitive)
        self._create_column_mapping(headers)

        # Convert rows to dictionaries
        tickets = []
        for row_idx, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
            try:
                ticket = self._parse_ticket_row(row, headers)
                if ticket:
                    tickets.append(ticket)
            except Exception as e:
                logger.warning(f"Failed to parse row {row_idx}: {e}")
                continue

        logger.info(f"Normalized {len(tickets)} tickets")
        return tickets

    def _create_column_mapping(self, headers: List[str]):
        """
        Create mapping from expected columns to actual column indices.

        Args:
            headers: List of column headers from sheet
        """
        self.column_mapping = {}

        for key, expected_name in self.EXPECTED_COLUMNS.items():
            # Find column index (case-insensitive)
            for i, header in enumerate(headers):
                if header.strip().lower() == expected_name.lower():
                    self.column_mapping[key] = i
                    break

        logger.debug(f"Column mapping: {self.column_mapping}")

    def _parse_ticket_row(self, row: List, headers: List[str]) -> Optional[Dict]:
        """
        Parse a single ticket row.

        Args:
            row: Row data
            headers: Column headers

        Returns:
            Dictionary with ticket data or None if invalid
        """

        def get_cell(key: str) -> str:
            """Get cell value by key."""
            idx = self.column_mapping.get(key)
            if idx is not None and idx < len(row):
                return row[idx].strip() if row[idx] else ''
            return ''

        # Parse basic fields
        title = get_cell('title')
        if not title:
            # Skip rows without title
            return None

        ticket = {
            'title': title,
            'priority': get_cell('priority'),
            'type': get_cell('type'),
            'assigned': get_cell('assigned'),
            'reported_by': get_cell('reported_by'),
            'duration': get_cell('duration'),
            'bucket': get_cell('bucket'),
            'github_issue': get_cell('github_issue'),
            'notes': get_cell('notes'),
            'root_cause_status': get_cell('root_cause_status')
        }

        # Parse dates
        ticket['reported_time'] = self._parse_datetime(get_cell('reported_time'))
        ticket['first_response_time'] = self._parse_datetime(get_cell('first_response_time'))
        ticket['closed_time'] = self._parse_datetime(get_cell('closed_time'))

        # Determine if ticket is closed
        ticket['is_closed'] = bool(ticket['closed_time'])

        return ticket

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        """
        Parse datetime string in M/D/Y T(24) format.

        Args:
            date_str: Date string (e.g., "1/15/2025 14:30")

        Returns:
            Parsed datetime or None if invalid
        """
        if not date_str:
            return None

        # Try various date formats
        formats = [
            '%m/%d/%Y %H:%M',      # 1/15/2025 14:30
            '%m/%d/%Y %H:%M:%S',   # 1/15/2025 14:30:00
            '%m/%d/%y %H:%M',      # 1/15/25 14:30
            '%Y-%m-%d %H:%M:%S',   # 2025-01-15 14:30:00
            '%Y-%m-%d',            # 2025-01-15
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.debug(f"Failed to parse date: {date_str}")
        return None


class TicketMetricsCalculator:
    """Calculate metrics from ticket data."""

    def __init__(self, tickets: List[Dict]):
        """
        Initialize ticket metrics calculator.

        Args:
            tickets: List of ticket dictionaries
        """
        self.tickets = tickets

    def calculate_metrics_by_user(self) -> Dict:
        """
        Calculate ticket metrics grouped by assigned user.

        Returns:
            Dictionary mapping username to ticket metrics
        """
        user_metrics = defaultdict(lambda: {
            'total_tickets': 0,
            'tickets_open': 0,
            'tickets_closed': 0,
            'tickets_high_priority': 0,
            'tickets_medium_priority': 0,
            'tickets_low_priority': 0,
            'ticket_types': defaultdict(int),
            'resolution_times': [],
            'first_response_times': [],
            'tickets_with_github_issue': 0
        })

        for ticket in self.tickets:
            assigned = ticket.get('assigned', '').strip()
            if not assigned:
                continue

            metrics = user_metrics[assigned]
            metrics['total_tickets'] += 1

            # Open vs Closed
            if ticket.get('is_closed'):
                metrics['tickets_closed'] += 1
            else:
                metrics['tickets_open'] += 1

            # Priority
            priority = ticket.get('priority', '').lower()
            if 'high' in priority:
                metrics['tickets_high_priority'] += 1
            elif 'medium' in priority or 'med' in priority:
                metrics['tickets_medium_priority'] += 1
            elif 'low' in priority:
                metrics['tickets_low_priority'] += 1

            # Type
            ticket_type = ticket.get('type', '').strip()
            if ticket_type:
                metrics['ticket_types'][ticket_type] += 1

            # Resolution time
            if ticket.get('reported_time') and ticket.get('closed_time'):
                resolution_hours = calculate_hours_between(
                    ticket['reported_time'].isoformat(),
                    ticket['closed_time'].isoformat()
                )
                metrics['resolution_times'].append(resolution_hours)

            # First response time
            if ticket.get('reported_time') and ticket.get('first_response_time'):
                response_hours = calculate_hours_between(
                    ticket['reported_time'].isoformat(),
                    ticket['first_response_time'].isoformat()
                )
                metrics['first_response_times'].append(response_hours)

            # GitHub Issue
            if ticket.get('github_issue'):
                metrics['tickets_with_github_issue'] += 1

        # Calculate averages
        result = {}
        for username, metrics in user_metrics.items():
            result[username] = {
                'total_tickets': metrics['total_tickets'],
                'tickets_open': metrics['tickets_open'],
                'tickets_closed': metrics['tickets_closed'],
                'tickets_high_priority': metrics['tickets_high_priority'],
                'tickets_medium_priority': metrics['tickets_medium_priority'],
                'tickets_low_priority': metrics['tickets_low_priority'],
                'ticket_types': dict(metrics['ticket_types']),
                'avg_resolution_time_hours': round(
                    sum(metrics['resolution_times']) / len(metrics['resolution_times']), 1
                ) if metrics['resolution_times'] else 0,
                'avg_first_response_time_hours': round(
                    sum(metrics['first_response_times']) / len(metrics['first_response_times']), 1
                ) if metrics['first_response_times'] else 0,
                'tickets_with_github_issue': metrics['tickets_with_github_issue']
            }

        return result

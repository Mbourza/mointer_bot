import os
from pathlib import Path

class Config:
    # Base directories
    BASE_DIR = Path("/www/wwwroot/MointorService")
    DATA_DIR = BASE_DIR / "data"
    INPUT_DIR = DATA_DIR / "input"
    PROCESSED_DIR = DATA_DIR / "processed"
    LOG_DIR = DATA_DIR / "logs"
    
    # File paths
    LOG_FILE = LOG_DIR / "bot.log"
    
    # Website monitoring settings
    WEBSITE_URL = os.getenv('WEBSITE_URL', 'https://www.majella.ma/dashboard/catalogue')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))
    MAX_CONSECUTIVE_ERRORS = int(os.getenv('MAX_CONSECUTIVE_ERRORS', '10'))
    
    # Google Sheets settings
    GOOGLE_SHEETS_ENABLED = os.getenv('GOOGLE_SHEETS_ENABLED', 'true').lower() == 'true'
    GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', str(BASE_DIR / 'credentials.json'))
    GOOGLE_SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID', '1qre78RXDGYR3KXm_Kv9-vA_TabpkCWCm-tulcQRkg7c')
    GOOGLE_SPREADSHEET_URL = os.getenv('GOOGLE_SPREADSHEET_URL', 'https://docs.google.com/spreadsheets/d/1qre78RXDGYR3KXm_Kv9-vA_TabpkCWCm-tulcQRkg7c/')
    
    # Which sheets to monitor (comma-separated)
    sheets_to_monitor = os.getenv('GOOGLE_SHEETS_TO_MONITOR', '')
    GOOGLE_SHEETS_TO_MONITOR = [s.strip() for s in sheets_to_monitor.split(',') if s.strip()] if sheets_to_monitor else []
    
    # Column configuration (0-based indices)
    REFERENCES_COLUMN_INDEX = int(os.getenv('REFERENCES_COLUMN_INDEX', '6'))  # Column G
    STATUS_COLUMN_INDEX = int(os.getenv('STATUS_COLUMN_INDEX', '7'))          # Column H
    NOTES_COLUMN_INDEX = int(os.getenv('NOTES_COLUMN_INDEX', '8'))            # Column I
    
    # Excel settings (keep for backward compatibility)
    EXCEL_REFERENCE_COLUMN = os.getenv('EXCEL_REFERENCE_COLUMN', 'Reference')
    EXCEL_SKU_COLUMN = os.getenv('EXCEL_SKU_COLUMN', 'SKU')
    EXCEL_SUPPLIER_COLUMN = os.getenv('EXCEL_SUPPLIER_COLUMN', 'Supplier')
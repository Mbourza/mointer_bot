#!/usr/bin/env python3
"""
Supplier Monitor Bot - Google Sheets Only Version with Playwright
"""

import os
import time
import signal
import sys
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from config import Config
from google_sheets_handler import GoogleSheetsHandler
from website_monitor import WebsiteMonitor
from logger import setup_logger

# Load environment variables
load_dotenv()

class SupplierMonitorBot:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger('supplier_bot', self.config.LOG_FILE)
        
        # Initialize handlers
        self.sheets_handler = GoogleSheetsHandler(self.config, self.logger)
        self.website_monitor = WebsiteMonitor(self.config, self.logger)
        
        self.running = True
        self.last_check_time = 0
        self.processing_active = False
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        
    def start(self):
        """Start the bot"""
        self.logger.info("=" * 60)
        self.logger.info("🚗 SUPPLIER MONITOR BOT STARTED")
        self.logger.info(f"📊 PID: {os.getpid()}")
        self.logger.info(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        # Debug lines to check configuration
        self.logger.info(f"🔍 CONFIG CHECK: GOOGLE_SHEETS_ENABLED = {self.config.GOOGLE_SHEETS_ENABLED}")
        self.logger.info(f"🔍 CONFIG CHECK: GOOGLE_CREDENTIALS_PATH = {self.config.GOOGLE_CREDENTIALS_PATH}")
        self.logger.info(f"🔍 CONFIG CHECK: GOOGLE_SPREADSHEET_ID = {self.config.GOOGLE_SPREADSHEET_ID}")
        
        # Check if credentials file exists
        if Path(self.config.GOOGLE_CREDENTIALS_PATH).exists():
            self.logger.info(f"✅ Credentials file exists at: {self.config.GOOGLE_CREDENTIALS_PATH}")
        else:
            self.logger.error(f"❌ Credentials file NOT FOUND at: {self.config.GOOGLE_CREDENTIALS_PATH}")
            self.logger.error("Please place your Google Sheets credentials file in the correct location")
            sys.exit(1)
        
        # Create necessary directories
        self._create_directories()
        
        # Initialize Google Sheets if enabled
        if self.config.GOOGLE_SHEETS_ENABLED:
            self.logger.info("📊 Attempting to initialize Google Sheets...")
            self._init_google_sheets()
        else:
            self.logger.info("📊 Google Sheets is DISABLED in config")
            
        # Start main monitoring loop
        self._monitoring_loop()
        
    def _create_directories(self):
        """Create required directories"""
        directories = [
            self.config.LOG_DIR,
            self.config.PROCESSED_DIR,
            self.config.DATA_DIR
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"📁 Directory ensured: {directory}")
    
    def _init_google_sheets(self):
        """Initialize Google Sheets connection"""
        self.logger.info("=" * 40)
        self.logger.info("📊 INITIALIZING GOOGLE SHEETS")
        self.logger.info("=" * 40)
        
        # Authenticate
        self.logger.info("🔑 Step 1: Authenticating...")
        if not self.sheets_handler.authenticate(self.config.GOOGLE_CREDENTIALS_PATH):
            self.logger.error("❌ Failed to authenticate with Google Sheets")
            self.logger.info("=" * 40)
            return
        
        self.logger.info("✅ Authentication successful")
        
        # Open spreadsheet
        spreadsheet_target = self.config.GOOGLE_SPREADSHEET_URL or self.config.GOOGLE_SPREADSHEET_ID
        self.logger.info(f"📄 Step 2: Opening spreadsheet with ID: {spreadsheet_target}")
        
        if not spreadsheet_target:
            self.logger.error("❌ No spreadsheet ID or URL configured")
            self.logger.info("=" * 40)
            return
        
        if not self.sheets_handler.open_spreadsheet(spreadsheet_target):
            self.logger.error("❌ Failed to open spreadsheet")
            self.logger.info("=" * 40)
            return
        
        self.logger.info("✅ Spreadsheet opened successfully")
        
        # Load initial references
        self.logger.info("📋 Step 3: Loading references...")
        self._load_google_sheets_references()
        
        self.logger.info("✅ Google Sheets initialized successfully")
        self.logger.info("=" * 40)
    
    def _load_google_sheets_references(self):
        """Load references from Google Sheets"""
        self.logger.info("📥 Loading references from Google Sheets...")
        
        # Determine which sheets to monitor
        sheets_to_check = self.config.GOOGLE_SHEETS_TO_MONITOR if self.config.GOOGLE_SHEETS_TO_MONITOR else None
        
        # If specific sheets are configured, load each one
        if sheets_to_check:
            all_references = []
            for sheet_name in sheets_to_check:
                self.logger.info(f"📑 Checking sheet: {sheet_name}")
                df = self.sheets_handler.get_references_as_dataframe(sheet_name)
                if not df.empty:
                    self.website_monitor.add_google_sheet_references(df, sheet_name)
                    all_references.append(len(df))
                    self.logger.info(f"   ✅ Found {len(df)} references in {sheet_name}")
            
            if all_references:
                self.logger.info(f"✅ Loaded {sum(all_references)} references from {len(sheets_to_check)} sheets")
        else:
            # Load all sheets
            df = self.sheets_handler.get_references_as_dataframe()
            if not df.empty:
                self.website_monitor.add_google_sheet_references(df, "all_sheets")
                self.logger.info(f"✅ Loaded {len(df)} references from all sheets")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        consecutive_errors = 0
        loop_count = 0
        
        self.logger.info("🔄 Starting main monitoring loop")
        self.logger.info(f"⏱️ Check interval: {self.config.CHECK_INTERVAL} seconds")
        
        while self.running:
            loop_count += 1
            try:
                # Check for new references in Google Sheets periodically
                current_time = time.time()
                if (self.config.GOOGLE_SHEETS_ENABLED and 
                    current_time - self.last_check_time > 300):  # Check every 5 minutes
                    self.logger.info("🔄 Refreshing Google Sheets references...")
                    self._refresh_google_sheets()
                    self.last_check_time = current_time
                
                # Check website for updates - this will start processing if not already active
                if not self.processing_active:
                    self.logger.info(f"🔄 Check #{loop_count}: Checking for updates...")
                    self.website_monitor.check_for_updates()
                    self.processing_active = True
                else:
                    self.logger.debug(f"🔄 Check #{loop_count}: Processing already active")
                
                # Reset error counter on successful check
                consecutive_errors = 0
                
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"❌ Error in monitoring loop: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                
                if consecutive_errors >= self.config.MAX_CONSECUTIVE_ERRORS:
                    self.logger.critical(f"💥 Too many consecutive errors ({consecutive_errors}). Stopping bot.")
                    self.shutdown()
                    break
                    
            # Wait before next check
            time.sleep(self.config.CHECK_INTERVAL)
    
    def _refresh_google_sheets(self):
        """Refresh references from Google Sheets"""
        self.logger.info("🔄 Refreshing Google Sheets references...")
        self._load_google_sheets_references()
    
    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown"""
        self.logger.info("=" * 60)
        self.logger.info("🛑 SHUTTING DOWN SUPPLIER MONITOR BOT")
        self.logger.info("=" * 60)
        
        self.running = False
        
        # Shutdown website monitor (Playwright)
        if hasattr(self, 'website_monitor'):
            self.logger.info("🛑 Stopping website monitor...")
            self.website_monitor.shutdown()
        
        self.logger.info(f"📊 Final statistics:")
        self.logger.info(f"   Total processed: {len(self.website_monitor.processed_refs) if hasattr(self, 'website_monitor') else 0}")
        self.logger.info(f"   Queue remaining: {len(self.website_monitor.search_queue) if hasattr(self, 'website_monitor') else 0}")
        
        self.logger.info("✅ Bot stopped successfully")
        self.logger.info("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    bot = SupplierMonitorBot()
    bot.start()
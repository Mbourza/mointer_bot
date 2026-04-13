import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path
import json

class GoogleSheetsHandler:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.client = None
        self.spreadsheet = None
        
    def authenticate(self, credentials_path=None):
        """Authenticate with Google Sheets API"""
        try:
            # Use credentials from config or default path
            if not credentials_path:
                credentials_path = self.config.GOOGLE_CREDENTIALS_PATH
            
            # Define the scope
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Load credentials
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                credentials_path, scope
            )
            
            # Authorize client
            self.client = gspread.authorize(creds)
            self.logger.info("✅ Google Sheets authentication successful")
            return True
            
        except FileNotFoundError:
            self.logger.error(f"❌ Credentials file not found: {credentials_path}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Authentication failed: {str(e)}")
            return False
    
    def open_spreadsheet(self, sheet_id_or_url):
        """Open a spreadsheet by ID or URL"""
        try:
            # Check if it's a URL or ID
            if 'docs.google.com' in sheet_id_or_url:
                # Extract ID from URL
                import re
                match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_id_or_url)
                if match:
                    sheet_id = match.group(1)
                    self.spreadsheet = self.client.open_by_key(sheet_id)
                else:
                    raise ValueError("Invalid Google Sheets URL")
            else:
                # Assume it's a spreadsheet ID
                self.spreadsheet = self.client.open_by_key(sheet_id_or_url)
            
            self.logger.info(f"✅ Opened spreadsheet: {self.spreadsheet.title}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to open spreadsheet: {str(e)}")
            return False
    
    def get_all_references(self, sheet_name=None):
        """
        Get all references from all sheets or a specific sheet
        Column G (index 6) contains the references
        """
        all_references = []
        
        try:
            # If specific sheet requested
            if sheet_name:
                worksheets = [self.spreadsheet.worksheet(sheet_name)]
                self.logger.info(f"📄 Reading sheet: {sheet_name}")
            else:
                # Get all worksheets
                worksheets = self.spreadsheet.worksheets()
                self.logger.info(f"📄 Found {len(worksheets)} sheets")
            
            for worksheet in worksheets:
                sheet_name = worksheet.title
                self.logger.info(f"  Processing sheet: {sheet_name}")
                
                # Get all values from the sheet
                all_data = worksheet.get_all_values()
                
                if not all_data:
                    self.logger.warning(f"    ⚠️ Sheet {sheet_name} is empty")
                    continue
                
                # Assume first row is header
                headers = all_data[0] if all_data else []
                data_rows = all_data[1:] if len(all_data) > 1 else []
                
                # Check if we have at least 7 columns (G is 7th)
                if len(headers) < 7:
                    self.logger.warning(f"    ⚠️ Sheet {sheet_name} has less than 7 columns")
                    continue
                
                # Column G is index 6
                ref_column_name = headers[6] if len(headers) > 6 else "Column G"
                
                # Extract references from column G
                for row_idx, row in enumerate(data_rows, start=2):  # Start from row 2 (after header)
                    if len(row) > 6 and row[6].strip():  # Check if column G has value
                        reference = row[6].strip()
                        all_references.append({
                            'reference': reference,
                            'sheet': sheet_name,
                            'row': row_idx,
                            'full_row': row,
                            'source': f"{self.spreadsheet.title}/{sheet_name}"
                        })
                
                self.logger.info(f"    ✅ Found {len([r for r in data_rows if len(r) > 6 and r[6].strip()])} references")
            
            self.logger.info(f"✅ Total references found across all sheets: {len(all_references)}")
            return all_references
            
        except Exception as e:
            self.logger.error(f"❌ Error reading references: {str(e)}")
            return []
    
    def get_references_as_dataframe(self, sheet_name=None):
        """Get references as pandas DataFrame"""
        references = self.get_all_references(sheet_name)
        
        if not references:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(references)
        
        # Add status column
        df['status'] = 'pending'
        df['attempts'] = 0
        
        return df
    
    def mark_reference_as_found(self, reference, sheet_name, row):
        """Mark a reference as found in the sheet"""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            
            # Add "FOUND" in column H (index 7) or whatever column you want
            # Assuming you want to mark it in column H
            cell = f"H{row}"
            worksheet.update(cell, "FOUND")
            
            self.logger.info(f"✅ Marked reference {reference} as found at {cell}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to mark reference: {str(e)}")
            return False
    
    def update_reference_status(self, reference, sheet_name, row, status, notes=""):
        """Update reference status in the sheet"""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            
            # Assuming column H for status, column I for notes
            status_cell = f"H{row}"
            notes_cell = f"I{row}"
            
            # Batch update for efficiency
            worksheet.batch_update([
                {
                    'range': status_cell,
                    'values': [[status]]
                },
                {
                    'range': notes_cell,
                    'values': [[notes]]
                }
            ])
            
            self.logger.info(f"✅ Updated status for {reference}: {status}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update status: {str(e)}")
            return False
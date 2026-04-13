from google_sheets_handler import GoogleSheetsHandler
from config import Config
from logger import setup_logger

config = Config()
logger = setup_logger('test', 'test.log')
handler = GoogleSheetsHandler(config, logger)

if handler.authenticate('credentials.json'):
    print('✅ Authentication successful')
    
    if handler.open_spreadsheet(config.GOOGLE_SPREADSHEET_ID):
        print('✅ Spreadsheet opened')
        
        references = handler.get_all_references()
        print(f'✅ Found {len(references)} references')
else:
    print('❌ Authentication failed')
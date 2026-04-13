# mointer_bot

Monitor Bot – AI Agent

Monitor Bot is an intelligent automation agent that connects your data sources and synchronizes them with your system in real time.

⚙️ How it works
Google Sheets Monitoring
The bot continuously watches a specified Google Sheet
It detects new rows or updates instantly
Data Extraction
When new data is added (e.g. car part reference, name, etc.)
The bot extracts key fields automatically
Smart Catalogue Search
The bot searches inside
👉 majella.ma catalogue
It matches the product using:
Reference (SKU / OEM)
Name
Brand
Data Enrichment
Retrieves full product details:
Product name
Price
Compatibility
Images
Specs
Database Sync
Automatically inserts (or updates) the product in your database
Avoids duplicates using SKU / barcode logic
🧠 Smart Features
✅ Real-time sync (no manual import)
✅ Duplicate detection (SKU / code_barres)
✅ Error handling (if product not found → flagged)
✅ Auto-formatting of data
✅ Can handle bulk rows instantly
🚀 Advanced Options (you can add later)
WhatsApp notification when new products are added
Admin validation before insert
Multi-catalogue support (not only majella)
AI matching (even if name is not exact)
Stock auto-update if sheet contains quantities
💡 Real Use Case (your context)

You (or supplier) drop new parts into Google Sheets →
Bot detects → searches in Majella → enriches → saves in DB → ready for sale in your system (Mangan / e-commerce / app)
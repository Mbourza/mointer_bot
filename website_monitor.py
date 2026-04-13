"""
Website Monitor with Playwright - Follows same pattern as UltraFastCarpartsScraper
Monitors majella.ma catalogue by searching references one by one
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import threading 
import re
import random
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError

class WebsiteMonitor:
    """Website Monitor following the same pattern as UltraFastCarpartsScraper"""
    
    BASE_URL = "https://www.majella.ma"
    DASHBOARD_URL = f"{BASE_URL}/dashboard/catalogue"
    LOGIN_URL = f"{BASE_URL}/"
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.search_queue = []
        self.found_results = {}
        self.processed_refs = set()
        
        # Login credentials
        self.username = "3125460g"
        self.password = "12345678"
        
        # Playwright state
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.is_logged_in = False
        self.browser_initialized = False
        
        # Session management
        self.last_login = None
        self.last_activity = None
        self.session_start = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        
        # Locks for thread safety
        self.connection_lock = asyncio.Lock()
        self.search_lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        
        # Session timeouts
        self.session_timeout = 7200  # 2 hours
        self.inactivity_timeout = 1800  # 30 minutes
        self.session_renewal_threshold = 6300  # 1h45
        
        # Performance tracking
        self.search_times = []
        self.avg_search_time = 0
        self.total_searches = 0
        self.successful_searches = 0
        self.failed_searches = 0
        
        # Statistics
        self.stats = {
            'total_queued': 0,
            'total_searched': 0,
            'total_found': 0,
            'total_not_found': 0,
            'total_errors': 0,
            'total_logins': 0,
            'uptime_start': time.time()
        }
        
        # Event loop for async operations
        self.loop = None
        self.loop_thread = None
        self.loop_ready = False
        self._is_shutting_down = False
        
        # Timeout settings (like in UltraFastCarpartsScraper)
        self.timeout = 30000  # 30 seconds
        self.navigation_timeout = 30000
        self.search_timeout = 30000
        
        # Start event loop
        self._start_event_loop()
        
        self.logger.info("✅ WebsiteMonitor initialized")
    
    def _start_event_loop(self):
        """Start asyncio event loop in background thread"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop_ready = True
            self.loop.run_forever()
        
        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        
        # Wait for loop to be ready
        timeout = 5
        start_time = time.time()
        while not self.loop_ready and time.time() - start_time < timeout:
            time.sleep(0.1)
    
    def _run_async(self, coro):
        """Run async coroutine from sync context"""
        if not self.loop or not self.loop.is_running():
            self.logger.error("❌ Event loop not running")
            return None
        
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        try:
            return future.result(timeout=300)
        except Exception as e:
            self.logger.error(f"❌ Async execution error: {e}")
            return None
    
    # ==================== Synchronous methods for bot ====================
    
    def add_google_sheet_references(self, df, sheet_name):
        """Add references from Google Sheets to search queue"""
        timestamp = datetime.now()
        refs_added = 0
        
        for _, row in df.iterrows():
            reference = str(row.get('reference', '')).strip()
            
            if reference and reference not in self.processed_refs:
                existing = [item for item in self.search_queue if item['reference'] == reference]
                if not existing:
                    item = {
                        'reference': reference,
                        'sheet': sheet_name,
                        'row': row.get('row', 0),
                        'row_data': row.to_dict() if hasattr(row, 'to_dict') else {},
                        'source': f"Google Sheets/{sheet_name}",
                        'added_at': timestamp.isoformat(),
                        'status': 'pending',
                        'attempts': 0,
                        'max_attempts': 3
                    }
                    self.search_queue.append(item)
                    refs_added += 1
        
        self.stats['total_queued'] += refs_added
        self.logger.info(f"📥 Added {refs_added} items from {sheet_name} to search queue")
        self.logger.info(f"📊 Queue size: {len(self.search_queue)}")
    
    def check_for_updates(self):
        """Main method called by bot - starts processing the queue"""
        if not self.search_queue:
            self.logger.debug("📭 No items in search queue")
            return
        
        self.logger.info(f"🚀 Starting queue processing - {len(self.search_queue)} items remaining")
        self._run_async(self._process_queue())
    
    def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("🛑 Shutting down website monitor...")
        self._is_shutting_down = True
        self._run_async(self._close())
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.logger.info("✅ Website monitor stopped")
    
    # ==================== Async methods (same pattern as UltraFastCarpartsScraper) ====================
    
    async def _close(self):
        """Close browser gracefully"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def _process_queue(self):
        """Process the search queue (called by check_for_updates)"""
        self.logger.info("🚀 Starting queue processing...")
        
        # Setup browser and login first
        if not await self._setup_browser():
            self.logger.error("❌ Failed to setup browser")
            return
        
        if not await self._ensure_logged_in():
            self.logger.error("❌ Failed to login")
            return
        
        # Process items one by one
        items_to_process = list(self.search_queue)
        total_items = len(items_to_process)
        
        for index, item in enumerate(items_to_process):
            if self._is_shutting_down:
                break
            
            # Skip if already processed
            if item['reference'] in self.processed_refs:
                if item in self.search_queue:
                    self.search_queue.remove(item)
                continue
            
            # Check attempts
            if item['attempts'] >= item['max_attempts']:
                self.logger.warning(f"⚠️ Max attempts reached for {item['reference']}")
                if item in self.search_queue:
                    self.search_queue.remove(item)
                self.processed_refs.add(item['reference'])
                self.stats['total_errors'] += 1
                continue
            
            self.logger.info(f"📌 Processing {index + 1}/{total_items}: {item['reference']}")
            item['attempts'] += 1
            
            # Perform search
            result = await self._search_reference(item['reference'])
            
            if result.get('success'):
                if result.get('found'):
                    await self._handle_found(item, result)
                else:
                    await self._handle_not_found(item, result)
            else:
                self.logger.warning(f"⚠️ Search failed for {item['reference']}")
                self.consecutive_failures += 1
                self.stats['total_errors'] += 1
            
            # Small delay between searches
            await asyncio.sleep(2)
        
        self.logger.info("✅ Queue processing complete!")
        self._log_stats()
    
    async def _setup_browser(self) -> bool:
        """Setup ultra-optimized browser (like UltraFastCarpartsScraper)"""
        if self.browser_initialized:
            return True
        
        try:
            self.logger.info("🚀 Initializing browser...")
            
            self.playwright = await async_playwright().start()
            
            # Browser args from successful scraper
            browser_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-component-extensions-with-background-pages",
                "--disable-default-apps",
                "--mute-audio",
                "--no-first-run",
                "--no-zygote",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            ]
            
            self.browser = await self.playwright.chromium.launch(
                headless=True,  # True for VPS
                args=browser_args,
                timeout=60000
            )
            
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                java_script_enabled=True,
                bypass_csp=True,
                ignore_https_errors=True,
                accept_downloads=False,
                locale="fr-FR",
                timezone_id="Europe/Paris",
            )
            
            # Block unnecessary resources
            await self.context.route("**/*{analytics,tracking,adservice,doubleclick,facebook,google-analytics}*", 
                                     lambda route: route.abort())
            
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            self.page.set_default_navigation_timeout(self.navigation_timeout)
            
            self.browser_initialized = True
            self.logger.info("✅ Browser initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Browser setup failed: {e}")
            return False
    
    async def _ensure_logged_in(self) -> bool:
        """Ensure we are logged in (like ensure_connected in scraper)"""
        async with self.connection_lock:
            # Check if already logged in
            if self.is_logged_in:
                should_renew, reason = self._should_renew_session()
                if not should_renew:
                    # Verify we're on the right page
                    try:
                        current_url = self.page.url
                        if "catalogue" in current_url or "dashboard" in current_url:
                            # Check if search input exists
                            search_field = await self._find_search_field()
                            if search_field:
                                self.last_activity = time.time()
                                return True
                    except:
                        pass
            
            # Need to login
            return await self._perform_login()
    
    async def _perform_login(self, force_new: bool = False) -> bool:
        """Perform login (like in scraper)"""
        async with self.login_lock:
            try:
                self.logger.info("🔑 Logging in...")
                
                if force_new:
                    await self.context.clear_cookies()
                
                # Go to login page
                await self.page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                await asyncio.sleep(2)
                
                # Check if already logged in
                if "catalogue" in self.page.url or "dashboard" in self.page.url:
                    self.is_logged_in = True
                    self.last_login = time.time()
                    self.session_start = self.last_login
                    self.last_activity = self.last_login
                    self.stats['total_logins'] += 1
                    self.logger.info("✅ Already logged in")
                    return True
                
                # Wait for login form
                await self.page.wait_for_selector("#username", timeout=15000)
                await self.page.wait_for_selector("#password", timeout=15000)
                
                # Fill credentials
                await self.page.fill("#username", self.username)
                await asyncio.sleep(0.5)
                await self.page.fill("#password", self.password)
                await asyncio.sleep(0.5)
                
                # Check remember me
                await self.page.check("#rememberMe")
                
                # Click login
                login_button = await self.page.wait_for_selector("button[type='submit'].btn-login", timeout=10000)
                await login_button.click()
                
                # Wait for navigation
                await self.page.wait_for_load_state("networkidle", timeout=self.navigation_timeout)
                await asyncio.sleep(3)
                
                # Verify login
                current_url = self.page.url
                self.logger.info(f"📍 URL after login: {current_url}")
                
                if "catalogue" in current_url or "dashboard" in current_url:
                    self.is_logged_in = True
                    self.last_login = time.time()
                    self.session_start = self.last_login
                    self.last_activity = self.last_login
                    self.stats['total_logins'] += 1
                    self.consecutive_failures = 0
                    self.logger.info("🎉 Login successful!")
                    
                    # Navigate to catalogue
                    await self._navigate_to_catalogue()
                    return True
                
                self.logger.error(f"❌ Login failed - URL: {current_url}")
                return False
                
            except Exception as e:
                self.logger.error(f"❌ Login error: {e}")
                return False
    
    async def _navigate_to_catalogue(self) -> bool:
        """Navigate to catalogue page"""
        try:
            self.logger.info("📊 Navigating to catalogue...")
            
            await self.page.goto(self.DASHBOARD_URL, wait_until="domcontentloaded", timeout=self.navigation_timeout)
            await asyncio.sleep(3)
            
            # Wait for search field
            search_field = await self._find_search_field()
            if search_field:
                self.logger.info("✅ Successfully navigated to catalogue")
                self.last_activity = time.time()
                return True
            else:
                self.logger.warning("⚠️ Catalogue loaded but search field not found")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Navigation error: {e}")
            return False
    
    async def _find_search_field(self) -> Optional[object]:
        """Find search field with multiple strategies"""
        search_selectors = [
            "input[placeholder*='Rechercher']",
            "input[type='search']",
            "#search-input",
            "input[name='search']",
            ".search-input",
            "input[placeholder*='recherche']",
        ]
        
        for selector in search_selectors:
            try:
                field = self.page.locator(selector).first
                if await field.count() > 0:
                    if await field.is_visible():
                        self.logger.debug(f"✅ Found search field: {selector}")
                        return field
            except:
                continue
        
        # Last resort: scan all inputs
        try:
            all_inputs = await self.page.locator("input[type='text']").all()
            for input_field in all_inputs:
                if await input_field.is_visible():
                    placeholder = await input_field.get_attribute("placeholder") or ""
                    if "recherche" in placeholder.lower() or "search" in placeholder.lower():
                        return input_field
        except:
            pass
        
        self.logger.error("❌ No search field found")
        return None
    
    async def _search_reference(self, reference: str) -> Dict:
        """Search for a reference (like enhanced_search in scraper)"""
        start_time = time.time()
        
        async with self.search_lock:
            try:
                # Ensure we're on catalogue page
                if not await self._ensure_logged_in():
                    return {"success": False, "found": False, "error": "Not logged in"}
                
                # Find search field
                search_field = await self._find_search_field()
                if not search_field:
                    return {"success": False, "found": False, "error": "Search field not found"}
                
                # Clear and fill
                await search_field.fill("")
                await asyncio.sleep(0.5)
                await search_field.fill(reference)
                await asyncio.sleep(0.5)
                
                # Submit search (press Enter)
                await self.page.keyboard.press("Enter")
                
                # Wait for results
                self.logger.info(f"⏳ Waiting for results for '{reference}'...")
                
                # Wait for either results or "no results" message
                try:
                    await self.page.wait_for_function("""
                        () => {
                            const hasResults = document.querySelectorAll('.product-card-compact, .product-card').length > 0;
                            const hasNoResults = document.body.innerText.includes('Aucun produit trouvé') || 
                                                document.body.innerText.includes('No products found');
                            return hasResults || hasNoResults;
                        }
                    """, timeout=self.search_timeout)
                except PlaywrightTimeoutError:
                    self.logger.warning(f"⚠️ Timeout waiting for results for {reference}")
                
                await asyncio.sleep(2)  # Extra wait for dynamic content
                
                # Extract products
                products = await self._extract_products()
                
                response_time = round(time.time() - start_time, 3)
                self.search_times.append(response_time)
                if len(self.search_times) > 20:
                    self.search_times.pop(0)
                self.avg_search_time = sum(self.search_times) / len(self.search_times)
                
                self.total_searches += 1
                self.last_activity = time.time()
                
                if products:
                    self.successful_searches += 1
                    self.logger.info(f"✅ Found {len(products)} products for '{reference}' - {response_time}s")
                    return {
                        "success": True,
                        "found": True,
                        "products": products,
                        "product_count": len(products),
                        "response_time": response_time
                    }
                else:
                    # Check if no results message
                    page_text = await self.page.evaluate("document.body.innerText")
                    if "Aucun produit trouvé" in page_text or "No products found" in page_text:
                        self.logger.info(f"ℹ️ No products found for '{reference}' - {response_time}s")
                        return {
                            "success": True,
                            "found": False,
                            "products": [],
                            "product_count": 0,
                            "response_time": response_time
                        }
                    else:
                        self.logger.warning(f"⚠️ No products extracted for '{reference}'")
                        return {
                            "success": True,
                            "found": False,
                            "products": [],
                            "product_count": 0,
                            "response_time": response_time
                        }
                
            except Exception as e:
                self.failed_searches += 1
                self.logger.error(f"❌ Search error for '{reference}': {e}")
                return {"success": False, "found": False, "error": str(e)}
    
    async def _extract_products(self) -> List[Dict]:
        """Extract products from page (simplified version)"""
        try:
            products = await self.page.evaluate("""
                () => {
                    const products = [];
                    const cards = document.querySelectorAll('.product-card-compact, .product-card');
                    
                    cards.forEach((card, index) => {
                        try {
                            const product = {
                                reference: card.getAttribute('data-reference') || '',
                                name: '',
                                price: null,
                                image: null,
                                brand: '',
                                category: '',
                                stock_quantity: 0,
                                stock_status: 'unknown',
                                from_cache: false,
                                is_main_product: index === 0
                            };
                            
                            // Name
                            const title = card.querySelector('h3');
                            if (title) product.name = title.textContent?.trim() || '';
                            
                            // Reference
                            const refBadge = card.querySelector('.reference-badge');
                            if (refBadge) product.reference = refBadge.textContent?.trim() || product.reference;
                            
                            // Brand
                            const brand = card.querySelector('.meta-tag.brand-tag span');
                            if (brand) product.brand = brand.textContent?.trim() || '';
                            
                            // Price
                            const price = card.querySelector('.price-value');
                            if (price) {
                                const priceText = price.textContent?.replace(/[^0-9,.]/g, '').replace(',', '.') || '';
                                product.price = parseFloat(priceText) || null;
                            }
                            
                            // Image
                            const img = card.querySelector('img');
                            if (img && img.src) product.image = img.src;
                            
                            // Stock
                            const stockTotal = card.querySelector('.stock-total-value');
                            if (stockTotal) {
                                const match = stockTotal.textContent?.match(/\\d+/) || ['0'];
                                product.stock_quantity = parseInt(match[0]) || 0;
                                product.stock_status = product.stock_quantity > 0 ? 'in_stock' : 'out_of_stock';
                            }
                            
                            // Cache indicator
                            if (card.innerText.includes('cache')) product.from_cache = true;
                            
                            products.push(product);
                        } catch (e) {
                            console.error('Error extracting product:', e);
                        }
                    });
                    
                    return products;
                }
            """)
            return products
        except Exception as e:
            self.logger.error(f"❌ Error extracting products: {e}")
            return []
    
    async def _handle_found(self, item: Dict, result: Dict):
        """Handle found item"""
        item['status'] = 'found'
        item['found_at'] = datetime.now().isoformat()
        
        products = result.get('products', [])
        
        # Store in memory
        key = item['reference']
        if key not in self.found_results:
            self.found_results[key] = []
        self.found_results[key].append({
            'timestamp': item['found_at'],
            'products': products,
            'product_count': len(products)
        })
        
        # Save to file
        self._save_result(item, products)
        
        # Update stats
        if item in self.search_queue:
            self.search_queue.remove(item)
        self.processed_refs.add(item['reference'])
        self.stats['total_searched'] += 1
        self.stats['total_found'] += 1
    
    async def _handle_not_found(self, item: Dict, result: Dict):
        """Handle not found item"""
        item['status'] = 'not_found'
        item['not_found_at'] = datetime.now().isoformat()
        
        # Save to file
        self._save_result(item, None, found=False)
        
        # Update stats
        if item in self.search_queue:
            self.search_queue.remove(item)
        self.processed_refs.add(item['reference'])
        self.stats['total_searched'] += 1
        self.stats['total_not_found'] += 1
    
    def _save_result(self, item: Dict, products: Optional[List], found: bool = True):
        """Save result to file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            status = "found" if found else "not_found"
            filename = f"{status}_{item['reference']}_{timestamp}.json"
            filepath = self.config.PROCESSED_DIR / filename
            
            output = {
                'reference': item['reference'],
                'status': status,
                'timestamp': timestamp,
                'source': item.get('source', 'unknown'),
                'sheet': item.get('sheet', 'unknown'),
                'attempts': item['attempts'],
                'found_at': item.get('found_at') if found else None,
                'not_found_at': item.get('not_found_at') if not found else None,
                'products': products if found else None,
                'product_count': len(products) if found and products else 0
            }
            
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"💾 Saved: {filename}")
        except Exception as e:
            self.logger.error(f"❌ Error saving result: {e}")
    
    def _should_renew_session(self) -> Tuple[bool, str]:
        """Check if session needs renewal (like in scraper)"""
        if not self.is_logged_in:
            return True, "not_logged_in"
        
        current_time = time.time()
        
        if self.session_start:
            session_age = current_time - self.session_start
            if session_age > self.session_renewal_threshold:
                return True, f"session_old_{int(session_age)}s"
        
        if self.last_activity:
            inactivity = current_time - self.last_activity
            if inactivity > self.inactivity_timeout:
                return True, f"inactive_{int(inactivity)}s"
        
        return False, "healthy"
    
    def _log_stats(self):
        """Log statistics"""
        success_rate = (self.stats['total_found'] / max(self.stats['total_searched'], 1)) * 100
        
        self.logger.info("=" * 60)
        self.logger.info("📊 SEARCH STATISTICS")
        self.logger.info(f"   Total queued:    {self.stats['total_queued']}")
        self.logger.info(f"   Total searched:  {self.stats['total_searched']}")
        self.logger.info(f"   Found:           {self.stats['total_found']}")
        self.logger.info(f"   Not found:       {self.stats['total_not_found']}")
        self.logger.info(f"   Errors:          {self.stats['total_errors']}")
        self.logger.info(f"   Success rate:    {success_rate:.1f}%")
        self.logger.info(f"   Queue remaining: {len(self.search_queue)}")
        self.logger.info("=" * 60)
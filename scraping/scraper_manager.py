"""
Web scraper manager for coordinating multiple scraping components
"""
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from .base_scraper import BaseScraper, ScrapingStatus
from .pastebin_scraper import create_pastebin_scraper
from .github_scraper import create_github_scraper
from messaging.schemas import SourceType
from shared.config import settings
from shared.logging_config import logger


class ScrapingMode(str, Enum):
    """Scraping operation modes"""
    SEARCH_ONLY = "search_only"
    MONITOR_ONLY = "monitor_only"
    HYBRID = "hybrid"


@dataclass
class ScrapingTask:
    """Scraping task configuration"""
    task_id: str
    keywords: List[str]
    vips: List[str]
    sources: List[SourceType]
    mode: ScrapingMode
    duration: Optional[int] = None  # seconds, None for indefinite
    interval: int = 600  # seconds between scraping cycles
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class WebScraperManager:
    """Manages multiple web scrapers"""
    
    def __init__(self):
        self.scrapers: Dict[SourceType, BaseScraper] = {}
        self.scraping_tasks: Dict[str, ScrapingTask] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}
        
        # Callbacks
        self.message_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
        
        # Manager state
        self.is_running = False
        self._stop_event = asyncio.Event()
    
    async def initialize(self, sources: List[SourceType] = None):
        """Initialize scrapers for specified sources"""
        
        if sources is None:
            sources = [SourceType.PASTEBIN, SourceType.GITHUB]
        
        logger.info(f"Initializing web scrapers for: {[s.value for s in sources]}")
        
        initialization_results = {}
        
        for source in sources:
            try:
                scraper = await self._create_scraper(source)
                if scraper:
                    await scraper.start()
                    self.scrapers[source] = scraper
                    
                    # Set callbacks
                    scraper.set_message_callback(self._handle_message)
                    scraper.set_error_callback(self._handle_error)
                    
                    initialization_results[source] = "success"
                    logger.info(f"{source.value} scraper initialized successfully")
                else:
                    initialization_results[source] = "failed - configuration issue"
                    logger.warning(f"{source.value} scraper not initialized")
                    
            except Exception as e:
                initialization_results[source] = f"failed - {str(e)}"
                logger.error(f"Failed to initialize {source.value} scraper: {e}")
        
        self.is_running = True
        logger.info(f"Scraper manager initialized with {len(self.scrapers)} active scrapers")
        
        return initialization_results
    
    async def _create_scraper(self, source: SourceType) -> Optional[BaseScraper]:
        """Create scraper for specific source"""
        
        try:
            if source == SourceType.PASTEBIN:
                return create_pastebin_scraper()
            
            elif source == SourceType.GITHUB:
                github_token = getattr(settings, 'github_token', None)
                return create_github_scraper(github_token)
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating {source.value} scraper: {e}")
            return None
    
    async def start_scraping(self, 
                            task_id: str,
                            keywords: List[str],
                            vips: List[str] = None,
                            sources: List[SourceType] = None,
                            mode: ScrapingMode = ScrapingMode.HYBRID,
                            duration: Optional[int] = None,
                            interval: int = 600) -> bool:
        """Start scraping task"""
        
        if not self.is_running:
            raise RuntimeError("Scraper manager not initialized")
        
        if task_id in self.scraping_tasks:
            logger.warning(f"Scraping task {task_id} already exists")
            return False
        
        # Use all available sources if none specified
        if sources is None:
            sources = list(self.scrapers.keys())
        
        # Filter to only available sources
        available_sources = [s for s in sources if s in self.scrapers]
        
        if not available_sources:
            logger.error("No available sources for scraping")
            return False
        
        # Create scraping task
        task = ScrapingTask(
            task_id=task_id,
            keywords=keywords,
            vips=vips or [],
            sources=available_sources,
            mode=mode,
            duration=duration,
            interval=interval
        )
        
        self.scraping_tasks[task_id] = task
        
        # Start scraping based on mode
        try:
            if mode == ScrapingMode.SEARCH_ONLY:
                await self._start_search_scraping(task)
            elif mode == ScrapingMode.MONITOR_ONLY:
                await self._start_monitor_scraping(task)
            elif mode == ScrapingMode.HYBRID:
                await self._start_hybrid_scraping(task)
            
            logger.info(f"Started scraping task {task_id} with {len(available_sources)} sources")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scraping task {task_id}: {e}")
            del self.scraping_tasks[task_id]
            return False
    
    async def _start_search_scraping(self, task: ScrapingTask):
        """Start search-based scraping"""
        
        scraping_task = asyncio.create_task(
            self._run_search_scraping(task)
        )
        
        self.active_tasks[task.task_id] = scraping_task
    
    async def _start_monitor_scraping(self, task: ScrapingTask):
        """Start monitoring-based scraping"""
        
        monitor_tasks = []
        
        for source in task.sources:
            scraper = self.scrapers[source]
            
            # Create monitoring task for each scraper
            monitor_task = asyncio.create_task(
                self._run_scraper_monitoring(scraper, task)
            )
            monitor_tasks.append(monitor_task)
        
        # Store combined task
        self.active_tasks[task.task_id] = asyncio.create_task(
            asyncio.gather(*monitor_tasks, return_exceptions=True)
        )
    
    async def _start_hybrid_scraping(self, task: ScrapingTask):
        """Start hybrid scraping (search + monitoring)"""
        
        tasks = []
        
        # Add search task
        search_task = asyncio.create_task(
            self._run_search_scraping(task)
        )
        tasks.append(search_task)
        
        # Add monitoring tasks
        for source in task.sources:
            scraper = self.scrapers[source]
            monitor_task = asyncio.create_task(
                self._run_scraper_monitoring(scraper, task)
            )
            tasks.append(monitor_task)
        
        self.active_tasks[task.task_id] = asyncio.create_task(
            asyncio.gather(*tasks, return_exceptions=True)
        )
    
    async def _run_search_scraping(self, task: ScrapingTask):
        """Run search-based scraping"""
        
        start_time = datetime.utcnow()
        
        try:
            while not self._stop_event.is_set():
                current_time = datetime.utcnow()
                
                # Check duration limit
                if task.duration and (current_time - start_time).total_seconds() > task.duration:
                    break
                
                # Search on each source
                for source in task.sources:
                    scraper = self.scrapers[source]
                    
                    try:
                        # Search for each keyword
                        for keyword in task.keywords:
                            async for content_data in scraper.search_content(
                                query=keyword,
                                limit=20,
                                since=current_time - timedelta(seconds=task.interval)
                            ):
                                await self._handle_search_result(content_data, task.task_id, keyword)
                        
                        # Search for VIP mentions
                        for vip in task.vips:
                            async for content_data in scraper.search_content(
                                query=vip,
                                limit=20,
                                since=current_time - timedelta(seconds=task.interval)
                            ):
                                await self._handle_search_result(content_data, task.task_id, vip)
                        
                    except Exception as e:
                        logger.error(f"Search failed for {source.value}: {e}")
                
                # Wait before next search cycle
                await asyncio.sleep(task.interval)
                
        except Exception as e:
            logger.error(f"Search scraping failed for task {task.task_id}: {e}")
            raise
    
    async def _run_scraper_monitoring(self, scraper: BaseScraper, task: ScrapingTask):
        """Run monitoring for a specific scraper"""
        
        try:
            # Set up monitoring context
            scraper.monitored_vips = task.vips
            scraper.monitoring_keywords = task.keywords
            
            # Start monitoring
            await scraper.monitor_keywords(
                keywords=task.keywords,
                vips=task.vips,
                interval=task.interval,
                duration=task.duration
            )
            
        except Exception as e:
            logger.error(f"Monitoring failed for {scraper.source_type.value}: {e}")
            raise
    
    async def _handle_search_result(self, content_data: Dict[str, Any], task_id: str, keyword: str):
        """Handle search result"""
        
        task = self.scraping_tasks.get(task_id)
        if not task:
            return
        
        # Determine monitored VIP
        monitored_vip = self._extract_monitored_vip(content_data, task.vips)
        
        # Call registered callbacks
        for callback in self.message_callbacks:
            try:
                await callback(content_data, task_id, monitored_vip, keyword)
            except Exception as e:
                logger.error(f"Search callback failed: {e}")
    
    def _extract_monitored_vip(self, content_data: Dict[str, Any], vips: List[str]) -> Optional[str]:
        """Extract monitored VIP from content data"""
        
        content = content_data.get('content', '').lower()
        title = content_data.get('title', '').lower()
        
        for vip in vips:
            vip_lower = vip.lower()
            if vip_lower in content or vip_lower in title:
                return vip
        
        return None
    
    async def _handle_message(self, message):
        """Handle processed message from scraper"""
        # This is called by individual scrapers after they process content
        pass
    
    async def _handle_error(self, error, context):
        """Handle error from scraper"""
        logger.error(f"Scraper error: {error} (context: {context})")
        
        for callback in self.error_callbacks:
            try:
                await callback(error, context)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")
    
    async def stop_scraping(self, task_id: str) -> bool:
        """Stop specific scraping task"""
        
        if task_id not in self.scraping_tasks:
            logger.warning(f"Scraping task {task_id} not found")
            return False
        
        try:
            # Cancel active task
            if task_id in self.active_tasks:
                scraping_task = self.active_tasks[task_id]
                scraping_task.cancel()
                
                try:
                    await scraping_task
                except asyncio.CancelledError:
                    pass
                
                del self.active_tasks[task_id]
            
            # Remove task
            del self.scraping_tasks[task_id]
            
            logger.info(f"Stopped scraping task: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop scraping task {task_id}: {e}")
            return False
    
    async def stop_all_scraping(self):
        """Stop all scraping tasks"""
        
        task_ids = list(self.scraping_tasks.keys())
        
        for task_id in task_ids:
            await self.stop_scraping(task_id)
        
        logger.info("All scraping tasks stopped")
    
    async def shutdown(self):
        """Shutdown scraper manager"""
        
        try:
            # Stop all scraping
            await self.stop_all_scraping()
            
            # Stop all scrapers
            for source, scraper in self.scrapers.items():
                try:
                    await scraper.stop()
                    logger.info(f"Stopped {source.value} scraper")
                except Exception as e:
                    logger.error(f"Error stopping {source.value} scraper: {e}")
            
            self.scrapers.clear()
            self.is_running = False
            self._stop_event.set()
            
            logger.info("Scraper manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during scraper manager shutdown: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all scrapers and tasks"""
        
        scraper_status = {}
        for source, scraper in self.scrapers.items():
            scraper_status[source.value] = scraper.get_metrics()
        
        task_status = {}
        for task_id, task in self.scraping_tasks.items():
            task_status[task_id] = {
                'keywords': task.keywords,
                'vips': task.vips,
                'sources': [s.value for s in task.sources],
                'mode': task.mode.value,
                'duration': task.duration,
                'interval': task.interval,
                'created_at': task.created_at.isoformat(),
                'active': task_id in self.active_tasks
            }
        
        return {
            'manager_running': self.is_running,
            'active_scrapers': len(self.scrapers),
            'active_tasks': len(self.scraping_tasks),
            'scrapers': scraper_status,
            'tasks': task_status
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all scrapers"""
        
        health_results = {
            'manager_status': 'healthy' if self.is_running else 'stopped',
            'scrapers': {},
            'overall_health': 'healthy'
        }
        
        unhealthy_count = 0
        
        for source, scraper in self.scrapers.items():
            try:
                scraper_health = await scraper.health_check()
                health_results['scrapers'][source.value] = scraper_health
                
                if scraper_health['status'] != 'healthy':
                    unhealthy_count += 1
                    
            except Exception as e:
                health_results['scrapers'][source.value] = {
                    'status': 'error',
                    'error': str(e)
                }
                unhealthy_count += 1
        
        # Determine overall health
        if unhealthy_count == 0:
            health_results['overall_health'] = 'healthy'
        elif unhealthy_count < len(self.scrapers):
            health_results['overall_health'] = 'degraded'
        else:
            health_results['overall_health'] = 'unhealthy'
        
        return health_results
    
    def add_message_callback(self, callback: Callable):
        """Add callback for processed messages"""
        self.message_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """Add callback for errors"""
        self.error_callbacks.append(callback)
    
    async def scrape_url_direct(self, url: str, source: SourceType = None) -> Optional[Dict[str, Any]]:
        """Directly scrape a specific URL"""
        
        # Determine source from URL if not specified
        if source is None:
            if 'pastebin.com' in url:
                source = SourceType.PASTEBIN
            elif 'github.com' in url:
                source = SourceType.GITHUB
            else:
                logger.error(f"Cannot determine source for URL: {url}")
                return None
        
        # Get appropriate scraper
        if source not in self.scrapers:
            logger.error(f"No scraper available for source: {source}")
            return None
        
        scraper = self.scrapers[source]
        
        try:
            return await scraper.scrape_url(url)
        except Exception as e:
            logger.error(f"Failed to scrape URL {url}: {e}")
            return None


# Global scraper manager instance
scraper_manager = WebScraperManager()
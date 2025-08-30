"""
Base scraper class for web scraping components
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import aiohttp
import hashlib
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from shared.logging_config import logger
from messaging.message_format import create_web_scraping_message
from messaging.schemas import SourceType, Priority
from messaging.producer import threat_producer


class ScrapingStatus(str, Enum):
    """Scraper status states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class ScrapingMetrics:
    """Scraper performance metrics"""
    pages_scraped: int = 0
    requests_made: int = 0
    rate_limit_hits: int = 0
    errors_encountered: int = 0
    last_activity: Optional[datetime] = None
    uptime_start: Optional[datetime] = None


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    requests_per_second: float = 1.0
    requests_per_minute: int = 30
    requests_per_hour: int = 1000
    delay_between_requests: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0


class BaseScraper(ABC):
    """Base class for web scrapers"""
    
    def __init__(self, 
                 source_type: SourceType,
                 base_url: str,
                 rate_limit_config: RateLimitConfig = None):
        self.source_type = source_type
        self.base_url = base_url
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        
        # State management
        self.status = ScrapingStatus.STOPPED
        self.metrics = ScrapingMetrics()
        
        # Configuration
        self.max_retries = 3
        self.timeout = 30
        self.user_agent = 'Aegis-ThreatMonitor/1.0 (Security Research)'
        
        # Rate limiting
        self.last_request_time = 0
        self.request_times = []
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self._stop_event = asyncio.Event()
        
        # Callbacks
        self.message_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        
        # Monitoring
        self.monitoring_keywords: List[str] = []
        self.monitored_vips: List[str] = []
    
    async def start(self):
        """Start the scraper"""
        try:
            self.status = ScrapingStatus.STARTING
            self.metrics.uptime_start = datetime.utcnow()
            
            # Initialize session
            await self._initialize_session()
            
            # Test connectivity
            if not await self._test_connectivity():
                raise ValueError("Cannot connect to target website")
            
            self.status = ScrapingStatus.RUNNING
            logger.info(f"{self.source_type} scraper started successfully")
            
        except Exception as e:
            self.status = ScrapingStatus.ERROR
            logger.error(f"Failed to start {self.source_type} scraper: {e}")
            raise
    
    async def stop(self):
        """Stop the scraper"""
        try:
            self._stop_event.set()
            self.status = ScrapingStatus.STOPPED
            
            if self.session:
                await self.session.close()
                self.session = None
            
            logger.info(f"{self.source_type} scraper stopped")
            
        except Exception as e:
            logger.error(f"Error stopping {self.source_type} scraper: {e}")
    
    async def _initialize_session(self):
        """Initialize HTTP session with proper headers"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=10)
        )
    
    async def _test_connectivity(self) -> bool:
        """Test connectivity to target website"""
        try:
            async with self.session.get(self.base_url) as response:
                return response.status < 400
        except Exception as e:
            logger.error(f"Connectivity test failed for {self.base_url}: {e}")
            return False
    
    async def _make_request(self, 
                           url: str, 
                           method: str = 'GET',
                           params: Dict[str, Any] = None,
                           data: Dict[str, Any] = None,
                           headers: Dict[str, str] = None) -> aiohttp.ClientResponse:
        """Make rate-limited HTTP request"""
        
        # Apply rate limiting
        await self._apply_rate_limit()
        
        # Prepare request
        request_headers = headers or {}
        
        try:
            self.metrics.requests_made += 1
            
            async with self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                headers=request_headers
            ) as response:
                
                # Handle rate limiting
                if response.status == 429:
                    await self._handle_rate_limit(response)
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=429,
                        message="Rate limited"
                    )
                
                # Update request tracking
                self.last_request_time = time.time()
                self.request_times.append(self.last_request_time)
                
                # Clean old request times (keep last hour)
                cutoff_time = self.last_request_time - 3600
                self.request_times = [t for t in self.request_times if t > cutoff_time]
                
                return response
                
        except Exception as e:
            self.metrics.errors_encountered += 1
            logger.error(f"Request failed for {url}: {e}")
            raise
    
    async def _apply_rate_limit(self):
        """Apply rate limiting before making request"""
        current_time = time.time()
        
        # Check requests per second
        if self.last_request_time > 0:
            time_since_last = current_time - self.last_request_time
            min_delay = 1.0 / self.rate_limit_config.requests_per_second
            
            if time_since_last < min_delay:
                delay = min_delay - time_since_last
                await asyncio.sleep(delay)
        
        # Check requests per minute
        minute_ago = current_time - 60
        recent_requests = len([t for t in self.request_times if t > minute_ago])
        
        if recent_requests >= self.rate_limit_config.requests_per_minute:
            delay = 60 - (current_time - min(self.request_times))
            if delay > 0:
                logger.warning(f"Rate limit: waiting {delay:.1f}s (requests per minute)")
                await asyncio.sleep(delay)
        
        # Check requests per hour
        hour_ago = current_time - 3600
        hourly_requests = len([t for t in self.request_times if t > hour_ago])
        
        if hourly_requests >= self.rate_limit_config.requests_per_hour:
            delay = 3600 - (current_time - min(self.request_times))
            if delay > 0:
                logger.warning(f"Rate limit: waiting {delay:.1f}s (requests per hour)")
                await asyncio.sleep(delay)
    
    async def _handle_rate_limit(self, response: aiohttp.ClientResponse):
        """Handle rate limit response"""
        self.metrics.rate_limit_hits += 1
        self.status = ScrapingStatus.RATE_LIMITED
        
        # Extract wait time from headers
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            wait_time = int(retry_after)
        else:
            wait_time = min(self.rate_limit_config.delay_between_requests * 
                          (self.rate_limit_config.backoff_factor ** self.metrics.rate_limit_hits),
                          self.rate_limit_config.max_delay)
        
        logger.warning(f"Rate limited, waiting {wait_time} seconds")
        await asyncio.sleep(wait_time)
        
        self.status = ScrapingStatus.RUNNING
    
    @abstractmethod
    async def search_content(self, 
                            query: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search for content matching query"""
        pass
    
    @abstractmethod
    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape content from specific URL"""
        pass
    
    async def parse_html(self, html_content: str, url: str) -> BeautifulSoup:
        """Parse HTML content with BeautifulSoup"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup
        except Exception as e:
            logger.error(f"Failed to parse HTML from {url}: {e}")
            raise
    
    async def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract clean text content from parsed HTML"""
        try:
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text and clean it
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to extract text content: {e}")
            return ""
    
    async def extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract all links from parsed HTML"""
        try:
            links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)
                links.append(absolute_url)
            
            return links
            
        except Exception as e:
            logger.error(f"Failed to extract links: {e}")
            return []
    
    async def calculate_content_hash(self, content: str) -> str:
        """Calculate hash of content for deduplication"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    async def process_scraped_data(self, 
                                  scraped_data: Dict[str, Any],
                                  monitored_vip: Optional[str] = None,
                                  search_query: Optional[str] = None) -> bool:
        """Process and publish scraped data"""
        try:
            # Create standardized message
            message = create_web_scraping_message(
                scraping_data=scraped_data,
                source=self.source_type,
                search_query=search_query,
                monitored_vip=monitored_vip,
                priority=self._determine_priority(scraped_data, monitored_vip)
            )
            
            # Publish message
            success = threat_producer.publish_web_scraping_data(
                data=message.data.dict(),
                source=self.source_type.value
            )
            
            if success:
                self.metrics.pages_scraped += 1
                self.metrics.last_activity = datetime.utcnow()
                
                # Call message callback if set
                if self.message_callback:
                    await self.message_callback(message)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to process scraped data: {e}")
            if self.error_callback:
                await self.error_callback(e, scraped_data)
            return False
    
    def _determine_priority(self, scraped_data: Dict[str, Any], 
                          monitored_vip: Optional[str] = None) -> Priority:
        """Determine message priority based on content"""
        
        # High priority for monitored VIPs
        if monitored_vip:
            return Priority.HIGH
        
        # Check for threat indicators
        content = scraped_data.get('content', '').lower()
        threat_keywords = [
            'leak', 'hack', 'breach', 'password', 'credential',
            'personal info', 'doxx', 'threat', 'kill', 'bomb',
            'scam', 'fraud', 'phishing'
        ]
        
        if any(keyword in content for keyword in threat_keywords):
            return Priority.HIGH
        
        # Check content length (longer content might be more significant)
        if len(content) > 5000:
            return Priority.MEDIUM
        
        return Priority.LOW
    
    async def monitor_keywords(self, 
                              keywords: List[str],
                              vips: List[str] = None,
                              interval: int = 300,
                              duration: Optional[int] = None):
        """Monitor keywords with periodic scraping"""
        
        self.monitoring_keywords = keywords
        self.monitored_vips = vips or []
        
        logger.info(f"Starting keyword monitoring: {keywords}")
        
        start_time = datetime.utcnow()
        
        try:
            while not self._stop_event.is_set():
                current_time = datetime.utcnow()
                
                # Check duration limit
                if duration and (current_time - start_time).total_seconds() > duration:
                    break
                
                # Search for each keyword
                for keyword in keywords:
                    try:
                        # Determine monitored VIP for this search
                        monitored_vip = self._extract_monitored_vip_from_keyword(keyword)
                        
                        # Search for content
                        async for content_data in self.search_content(
                            query=keyword,
                            limit=10,
                            since=current_time - timedelta(seconds=interval)
                        ):
                            await self.process_scraped_data(
                                scraped_data=content_data,
                                monitored_vip=monitored_vip,
                                search_query=keyword
                            )
                    
                    except Exception as e:
                        logger.error(f"Error monitoring keyword '{keyword}': {e}")
                
                # Wait before next cycle
                await asyncio.sleep(interval)
                
        except Exception as e:
            logger.error(f"Keyword monitoring failed: {e}")
            raise
    
    def _extract_monitored_vip_from_keyword(self, keyword: str) -> Optional[str]:
        """Extract monitored VIP from keyword"""
        keyword_lower = keyword.lower()
        
        for vip in self.monitored_vips:
            if vip.lower() in keyword_lower:
                return vip
        
        return None
    
    def _content_matches_vip(self, content: str, vips: List[str]) -> Optional[str]:
        """Check if content mentions any monitored VIPs"""
        content_lower = content.lower()
        
        for vip in vips:
            if vip.lower() in content_lower:
                return vip
        
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get scraper metrics"""
        uptime = None
        if self.metrics.uptime_start:
            uptime = (datetime.utcnow() - self.metrics.uptime_start).total_seconds()
        
        return {
            'status': self.status.value,
            'source_type': self.source_type.value,
            'pages_scraped': self.metrics.pages_scraped,
            'requests_made': self.metrics.requests_made,
            'rate_limit_hits': self.metrics.rate_limit_hits,
            'errors_encountered': self.metrics.errors_encountered,
            'last_activity': self.metrics.last_activity.isoformat() if self.metrics.last_activity else None,
            'uptime_seconds': uptime,
            'requests_per_minute': len([t for t in self.request_times if t > time.time() - 60]),
            'requests_per_hour': len(self.request_times)
        }
    
    def set_message_callback(self, callback: Callable):
        """Set callback for processed messages"""
        self.message_callback = callback
    
    def set_error_callback(self, callback: Callable):
        """Set callback for errors"""
        self.error_callback = callback
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        try:
            # Test connectivity
            is_connected = await self._test_connectivity()
            
            return {
                'status': 'healthy' if is_connected else 'unhealthy',
                'scraper_status': self.status.value,
                'site_accessible': is_connected,
                'metrics': self.get_metrics(),
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'scraper_status': self.status.value,
                'last_check': datetime.utcnow().isoformat()
            }
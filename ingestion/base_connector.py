"""
Base connector class for social media API integrations
"""
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable, AsyncGenerator
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import aiohttp
from shared.logging_config import logger
from messaging.message_format import create_social_media_message
from messaging.schemas import SourceType, Priority
from messaging.producer import get_threat_producer


class ConnectorStatus(str, Enum):
    """Connector status states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class RateLimitInfo:
    """Rate limit information"""
    requests_remaining: int
    reset_time: datetime
    limit_window: int  # seconds
    requests_per_window: int


@dataclass
class ConnectorMetrics:
    """Connector performance metrics"""
    messages_processed: int = 0
    api_calls_made: int = 0
    rate_limit_hits: int = 0
    errors_encountered: int = 0
    last_activity: Optional[datetime] = None
    uptime_start: Optional[datetime] = None


class BaseSocialMediaConnector(ABC):
    """Base class for social media API connectors"""
    
    def __init__(self, 
                 source_type: SourceType,
                 api_credentials: Dict[str, str],
                 rate_limit_config: Dict[str, Any] = None):
        self.source_type = source_type
        self.api_credentials = api_credentials
        self.rate_limit_config = rate_limit_config or {}
        
        # State management
        self.status = ConnectorStatus.STOPPED
        self.metrics = ConnectorMetrics()
        self.rate_limit_info: Optional[RateLimitInfo] = None
        
        # Configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.batch_size = 100
        self.monitoring_keywords: List[str] = []
        self.monitored_vips: List[str] = []
        
        # Callbacks
        self.message_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self._stop_event = asyncio.Event()
    
    async def start(self):
        """Start the connector"""
        try:
            self.status = ConnectorStatus.STARTING
            self.metrics.uptime_start = datetime.utcnow()
            
            # Initialize session
            await self._initialize_session()
            
            # Validate credentials
            if not await self._validate_credentials():
                raise ValueError("Invalid API credentials")
            
            # Setup rate limiting
            await self._setup_rate_limiting()
            
            self.status = ConnectorStatus.RUNNING
            logger.info(f"{self.source_type} connector started successfully")
            
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            logger.error(f"Failed to start {self.source_type} connector: {e}")
            raise
    
    async def stop(self):
        """Stop the connector"""
        try:
            self._stop_event.set()
            self.status = ConnectorStatus.STOPPED
            
            if self.session:
                await self.session.close()
                self.session = None
            
            logger.info(f"{self.source_type} connector stopped")
            
        except Exception as e:
            logger.error(f"Error stopping {self.source_type} connector: {e}")
    
    async def _initialize_session(self):
        """Initialize HTTP session with proper headers"""
        headers = await self._get_default_headers()
        timeout = aiohttp.ClientTimeout(total=30)
        
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout
        )
    
    @abstractmethod
    async def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for API requests"""
        pass
    
    @abstractmethod
    async def _validate_credentials(self) -> bool:
        """Validate API credentials"""
        pass
    
    @abstractmethod
    async def _setup_rate_limiting(self):
        """Setup rate limiting configuration"""
        pass
    
    @abstractmethod
    async def search_posts(self, 
                          query: str, 
                          limit: int = 100,
                          since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search for posts matching query"""
        pass
    
    @abstractmethod
    async def get_user_posts(self, 
                            user_id: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from specific user"""
        pass
    
    @abstractmethod
    async def stream_real_time(self, 
                              keywords: List[str],
                              callback: Callable) -> None:
        """Stream real-time posts matching keywords"""
        pass
    
    async def _make_api_request(self, 
                               url: str, 
                               method: str = 'GET',
                               params: Dict[str, Any] = None,
                               data: Dict[str, Any] = None,
                               headers: Dict[str, str] = None) -> Dict[str, Any]:
        """Make rate-limited API request"""
        
        # Check rate limits
        await self._check_rate_limits()
        
        # Prepare request
        request_headers = headers or {}
        
        try:
            self.metrics.api_calls_made += 1
            
            async with self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=request_headers
            ) as response:
                
                # Update rate limit info
                await self._update_rate_limit_info(response)
                
                # Handle response
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:  # Rate limited
                    await self._handle_rate_limit(response)
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=429,
                        message="Rate limited"
                    )
                else:
                    response.raise_for_status()
                    
        except Exception as e:
            self.metrics.errors_encountered += 1
            logger.error(f"API request failed: {e}")
            raise
    
    async def _check_rate_limits(self):
        """Check if we're within rate limits"""
        if not self.rate_limit_info:
            return
        
        if self.rate_limit_info.requests_remaining <= 0:
            wait_time = (self.rate_limit_info.reset_time - datetime.utcnow()).total_seconds()
            if wait_time > 0:
                self.status = ConnectorStatus.RATE_LIMITED
                logger.warning(f"Rate limited, waiting {wait_time:.1f} seconds")
                await asyncio.sleep(wait_time)
                self.status = ConnectorStatus.RUNNING
    
    async def _update_rate_limit_info(self, response: aiohttp.ClientResponse):
        """Update rate limit info from response headers"""
        # This will be implemented by specific connectors
        pass
    
    async def _handle_rate_limit(self, response: aiohttp.ClientResponse):
        """Handle rate limit response"""
        self.metrics.rate_limit_hits += 1
        self.status = ConnectorStatus.RATE_LIMITED
        
        # Extract wait time from headers (platform-specific)
        wait_time = await self._extract_rate_limit_wait_time(response)
        
        if wait_time:
            logger.warning(f"Rate limited, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)
        
        self.status = ConnectorStatus.RUNNING
    
    async def _extract_rate_limit_wait_time(self, response: aiohttp.ClientResponse) -> Optional[int]:
        """Extract rate limit wait time from response headers"""
        # Default implementation - override in specific connectors
        return 60  # Default 1 minute wait
    
    async def process_post_data(self, post_data: Dict[str, Any], 
                               monitored_vip: Optional[str] = None,
                               keywords: List[str] = None) -> bool:
        """Process and publish post data"""
        try:
            # Create standardized message
            message = create_social_media_message(
                post_data=post_data,
                source=self.source_type,
                monitored_vip=monitored_vip,
                keywords=keywords or [],
                priority=self._determine_priority(post_data, monitored_vip)
            )
            
            # Publish message
            success = get_threat_producer().publish_social_media_data(
                data=message.data.dict(),
                platform=self.source_type.value
            )
            
            if success:
                self.metrics.messages_processed += 1
                self.metrics.last_activity = datetime.utcnow()
                
                # Call message callback if set
                if self.message_callback:
                    await self.message_callback(message)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to process post data: {e}")
            if self.error_callback:
                await self.error_callback(e, post_data)
            return False
    
    def _determine_priority(self, post_data: Dict[str, Any], 
                          monitored_vip: Optional[str] = None) -> Priority:
        """Determine message priority based on content"""
        
        # High priority for monitored VIPs
        if monitored_vip:
            return Priority.HIGH
        
        # Check for threat indicators
        content = post_data.get('content', '').lower()
        threat_keywords = ['scam', 'hack', 'leak', 'threat', 'kill', 'bomb']
        
        if any(keyword in content for keyword in threat_keywords):
            return Priority.HIGH
        
        # Check engagement metrics
        likes = post_data.get('likes', 0)
        shares = post_data.get('shares', 0)
        
        if likes > 1000 or shares > 100:
            return Priority.MEDIUM
        
        return Priority.LOW
    
    async def monitor_keywords(self, keywords: List[str], 
                              vips: List[str] = None,
                              duration: Optional[int] = None):
        """Monitor keywords for specified duration"""
        
        self.monitoring_keywords = keywords
        self.monitored_vips = vips or []
        
        logger.info(f"Starting keyword monitoring: {keywords}")
        
        start_time = datetime.utcnow()
        
        try:
            # Start real-time streaming
            await self.stream_real_time(
                keywords=keywords,
                callback=self._handle_stream_message
            )
            
        except Exception as e:
            logger.error(f"Keyword monitoring failed: {e}")
            raise
    
    async def _handle_stream_message(self, message_data: Dict[str, Any]):
        """Handle incoming stream message"""
        try:
            # Determine if this relates to a monitored VIP
            monitored_vip = self._extract_monitored_vip(message_data)
            
            # Process the message
            await self.process_post_data(
                post_data=message_data,
                monitored_vip=monitored_vip,
                keywords=self.monitoring_keywords
            )
            
        except Exception as e:
            logger.error(f"Failed to handle stream message: {e}")
    
    def _extract_monitored_vip(self, message_data: Dict[str, Any]) -> Optional[str]:
        """Extract monitored VIP from message data"""
        content = message_data.get('content', '').lower()
        author = message_data.get('author_username', '').lower()
        
        for vip in self.monitored_vips:
            vip_lower = vip.lower()
            if vip_lower in content or vip_lower in author:
                return vip
        
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get connector metrics"""
        uptime = None
        if self.metrics.uptime_start:
            uptime = (datetime.utcnow() - self.metrics.uptime_start).total_seconds()
        
        return {
            'status': self.status.value,
            'source_type': self.source_type.value,
            'messages_processed': self.metrics.messages_processed,
            'api_calls_made': self.metrics.api_calls_made,
            'rate_limit_hits': self.metrics.rate_limit_hits,
            'errors_encountered': self.metrics.errors_encountered,
            'last_activity': self.metrics.last_activity.isoformat() if self.metrics.last_activity else None,
            'uptime_seconds': uptime,
            'rate_limit_info': {
                'requests_remaining': self.rate_limit_info.requests_remaining if self.rate_limit_info else None,
                'reset_time': self.rate_limit_info.reset_time.isoformat() if self.rate_limit_info else None
            } if self.rate_limit_info else None
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
            # Test API connectivity
            is_connected = await self._validate_credentials()
            
            return {
                'status': 'healthy' if is_connected else 'unhealthy',
                'connector_status': self.status.value,
                'api_connected': is_connected,
                'metrics': self.get_metrics(),
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'connector_status': self.status.value,
                'last_check': datetime.utcnow().isoformat()
            }
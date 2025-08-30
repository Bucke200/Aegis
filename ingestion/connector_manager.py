"""
Social media connector manager for coordinating multiple API connectors
"""
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from .base_connector import BaseSocialMediaConnector, ConnectorStatus
from .twitter_connector import create_twitter_connector
from .meta_connector import create_facebook_connector, create_instagram_connector
from .linkedin_connector import create_linkedin_connector
from messaging.schemas import SourceType
from shared.config import settings
from shared.logging_config import logger


class MonitoringMode(str, Enum):
    """Monitoring operation modes"""
    SEARCH_ONLY = "search_only"
    STREAM_ONLY = "stream_only"
    HYBRID = "hybrid"
    POLLING = "polling"


@dataclass
class MonitoringTask:
    """Monitoring task configuration"""
    task_id: str
    keywords: List[str]
    vips: List[str]
    platforms: List[SourceType]
    mode: MonitoringMode
    duration: Optional[int] = None  # seconds, None for indefinite
    interval: int = 300  # seconds between polls
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class SocialMediaConnectorManager:
    """Manages multiple social media API connectors"""
    
    def __init__(self):
        self.connectors: Dict[SourceType, BaseSocialMediaConnector] = {}
        self.monitoring_tasks: Dict[str, MonitoringTask] = {}
        self.active_streams: Dict[str, asyncio.Task] = {}
        
        # Callbacks
        self.message_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
        
        # Manager state
        self.is_running = False
        self._stop_event = asyncio.Event()
    
    async def initialize(self, platforms: List[SourceType] = None):
        """Initialize connectors for specified platforms"""
        
        if platforms is None:
            platforms = [SourceType.TWITTER, SourceType.FACEBOOK, SourceType.INSTAGRAM, SourceType.LINKEDIN]
        
        logger.info(f"Initializing social media connectors for: {[p.value for p in platforms]}")
        
        initialization_results = {}
        
        for platform in platforms:
            try:
                connector = await self._create_connector(platform)
                if connector:
                    await connector.start()
                    self.connectors[platform] = connector
                    
                    # Set callbacks
                    connector.set_message_callback(self._handle_message)
                    connector.set_error_callback(self._handle_error)
                    
                    initialization_results[platform] = "success"
                    logger.info(f"{platform.value} connector initialized successfully")
                else:
                    initialization_results[platform] = "failed - no credentials"
                    logger.warning(f"{platform.value} connector not initialized - missing credentials")
                    
            except Exception as e:
                initialization_results[platform] = f"failed - {str(e)}"
                logger.error(f"Failed to initialize {platform.value} connector: {e}")
        
        self.is_running = True
        logger.info(f"Connector manager initialized with {len(self.connectors)} active connectors")
        
        return initialization_results
    
    async def _create_connector(self, platform: SourceType) -> Optional[BaseSocialMediaConnector]:
        """Create connector for specific platform"""
        
        try:
            if platform == SourceType.TWITTER:
                if settings.twitter_bearer_token:
                    return create_twitter_connector()
                
            elif platform == SourceType.FACEBOOK:
                if settings.facebook_access_token:
                    return create_facebook_connector()
                
            elif platform == SourceType.INSTAGRAM:
                if settings.facebook_access_token and settings.instagram_business_account_id:
                    return create_instagram_connector()
                
            elif platform == SourceType.LINKEDIN:
                if settings.linkedin_access_token:
                    return create_linkedin_connector()
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating {platform.value} connector: {e}")
            return None
    
    async def start_monitoring(self, 
                              task_id: str,
                              keywords: List[str],
                              vips: List[str] = None,
                              platforms: List[SourceType] = None,
                              mode: MonitoringMode = MonitoringMode.HYBRID,
                              duration: Optional[int] = None) -> bool:
        """Start monitoring task"""
        
        if not self.is_running:
            raise RuntimeError("Connector manager not initialized")
        
        if task_id in self.monitoring_tasks:
            logger.warning(f"Monitoring task {task_id} already exists")
            return False
        
        # Use all available platforms if none specified
        if platforms is None:
            platforms = list(self.connectors.keys())
        
        # Filter to only available platforms
        available_platforms = [p for p in platforms if p in self.connectors]
        
        if not available_platforms:
            logger.error("No available platforms for monitoring")
            return False
        
        # Create monitoring task
        task = MonitoringTask(
            task_id=task_id,
            keywords=keywords,
            vips=vips or [],
            platforms=available_platforms,
            mode=mode,
            duration=duration
        )
        
        self.monitoring_tasks[task_id] = task
        
        # Start monitoring based on mode
        try:
            if mode == MonitoringMode.STREAM_ONLY:
                await self._start_streaming_monitoring(task)
            elif mode == MonitoringMode.SEARCH_ONLY:
                await self._start_search_monitoring(task)
            elif mode == MonitoringMode.HYBRID:
                await self._start_hybrid_monitoring(task)
            elif mode == MonitoringMode.POLLING:
                await self._start_polling_monitoring(task)
            
            logger.info(f"Started monitoring task {task_id} with {len(available_platforms)} platforms")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start monitoring task {task_id}: {e}")
            del self.monitoring_tasks[task_id]
            return False
    
    async def _start_streaming_monitoring(self, task: MonitoringTask):
        """Start real-time streaming monitoring"""
        
        stream_tasks = []
        
        for platform in task.platforms:
            connector = self.connectors[platform]
            
            # Create streaming task
            stream_task = asyncio.create_task(
                self._run_platform_stream(connector, task)
            )
            stream_tasks.append(stream_task)
        
        # Store tasks for management
        self.active_streams[task.task_id] = asyncio.create_task(
            asyncio.gather(*stream_tasks, return_exceptions=True)
        )
    
    async def _start_search_monitoring(self, task: MonitoringTask):
        """Start search-based monitoring"""
        
        search_task = asyncio.create_task(
            self._run_search_monitoring(task)
        )
        
        self.active_streams[task.task_id] = search_task
    
    async def _start_hybrid_monitoring(self, task: MonitoringTask):
        """Start hybrid monitoring (streaming + periodic search)"""
        
        # Start streaming for platforms that support it
        streaming_platforms = [SourceType.TWITTER]  # Twitter has best streaming support
        polling_platforms = [p for p in task.platforms if p not in streaming_platforms]
        
        tasks = []
        
        # Streaming tasks
        for platform in task.platforms:
            if platform in streaming_platforms and platform in self.connectors:
                connector = self.connectors[platform]
                stream_task = asyncio.create_task(
                    self._run_platform_stream(connector, task)
                )
                tasks.append(stream_task)
        
        # Polling tasks for other platforms
        if polling_platforms:
            polling_task = asyncio.create_task(
                self._run_polling_monitoring(task, polling_platforms)
            )
            tasks.append(polling_task)
        
        self.active_streams[task.task_id] = asyncio.create_task(
            asyncio.gather(*tasks, return_exceptions=True)
        )
    
    async def _start_polling_monitoring(self, task: MonitoringTask):
        """Start polling-based monitoring"""
        
        polling_task = asyncio.create_task(
            self._run_polling_monitoring(task, task.platforms)
        )
        
        self.active_streams[task.task_id] = polling_task
    
    async def _run_platform_stream(self, connector: BaseSocialMediaConnector, task: MonitoringTask):
        """Run streaming for a specific platform"""
        
        try:
            logger.info(f"Starting stream for {connector.source_type.value} with keywords: {task.keywords}")
            
            # Set up monitoring context
            connector.monitored_vips = task.vips
            connector.monitoring_keywords = task.keywords
            
            # Start streaming
            await connector.stream_real_time(
                keywords=task.keywords,
                callback=lambda msg: self._handle_stream_message(msg, task.task_id)
            )
            
        except Exception as e:
            logger.error(f"Streaming failed for {connector.source_type.value}: {e}")
            raise
    
    async def _run_search_monitoring(self, task: MonitoringTask):
        """Run search-based monitoring"""
        
        start_time = datetime.utcnow()
        last_search = {}
        
        try:
            while not self._stop_event.is_set():
                current_time = datetime.utcnow()
                
                # Check duration limit
                if task.duration and (current_time - start_time).total_seconds() > task.duration:
                    break
                
                # Search on each platform
                for platform in task.platforms:
                    connector = self.connectors[platform]
                    
                    try:
                        # Determine search timeframe
                        since_time = last_search.get(platform, current_time - timedelta(minutes=30))
                        
                        # Search for each keyword
                        for keyword in task.keywords:
                            async for post_data in connector.search_posts(
                                query=keyword,
                                limit=50,
                                since=since_time
                            ):
                                await self._handle_search_result(post_data, task.task_id, keyword)
                        
                        # Search for VIP mentions
                        for vip in task.vips:
                            async for post_data in connector.search_posts(
                                query=vip,
                                limit=50,
                                since=since_time
                            ):
                                await self._handle_search_result(post_data, task.task_id, vip)
                        
                        last_search[platform] = current_time
                        
                    except Exception as e:
                        logger.error(f"Search failed for {platform.value}: {e}")
                
                # Wait before next search cycle
                await asyncio.sleep(task.interval)
                
        except Exception as e:
            logger.error(f"Search monitoring failed for task {task.task_id}: {e}")
            raise
    
    async def _run_polling_monitoring(self, task: MonitoringTask, platforms: List[SourceType]):
        """Run polling monitoring for specific platforms"""
        
        start_time = datetime.utcnow()
        
        try:
            while not self._stop_event.is_set():
                current_time = datetime.utcnow()
                
                # Check duration limit
                if task.duration and (current_time - start_time).total_seconds() > task.duration:
                    break
                
                # Poll each platform
                for platform in platforms:
                    if platform not in self.connectors:
                        continue
                    
                    connector = self.connectors[platform]
                    
                    try:
                        # Use connector's streaming method which handles polling for non-streaming APIs
                        await connector.stream_real_time(
                            keywords=task.keywords,
                            callback=lambda msg: self._handle_stream_message(msg, task.task_id)
                        )
                        
                    except Exception as e:
                        logger.error(f"Polling failed for {platform.value}: {e}")
                
                # Wait before next poll
                await asyncio.sleep(task.interval)
                
        except Exception as e:
            logger.error(f"Polling monitoring failed for task {task.task_id}: {e}")
            raise
    
    async def _handle_stream_message(self, message_data: Dict[str, Any], task_id: str):
        """Handle message from streaming"""
        
        task = self.monitoring_tasks.get(task_id)
        if not task:
            return
        
        # Determine monitored VIP
        monitored_vip = self._extract_monitored_vip(message_data, task.vips)
        
        # Process message through connector
        # The connector will handle message creation and publishing
        
        # Call registered callbacks
        for callback in self.message_callbacks:
            try:
                await callback(message_data, task_id, monitored_vip)
            except Exception as e:
                logger.error(f"Message callback failed: {e}")
    
    async def _handle_search_result(self, post_data: Dict[str, Any], task_id: str, keyword: str):
        """Handle search result"""
        
        task = self.monitoring_tasks.get(task_id)
        if not task:
            return
        
        # Determine monitored VIP
        monitored_vip = self._extract_monitored_vip(post_data, task.vips)
        
        # Call registered callbacks
        for callback in self.message_callbacks:
            try:
                await callback(post_data, task_id, monitored_vip, keyword)
            except Exception as e:
                logger.error(f"Search callback failed: {e}")
    
    def _extract_monitored_vip(self, message_data: Dict[str, Any], vips: List[str]) -> Optional[str]:
        """Extract monitored VIP from message data"""
        
        content = message_data.get('content', '').lower()
        author = message_data.get('author_username', '').lower()
        
        for vip in vips:
            vip_lower = vip.lower()
            if vip_lower in content or vip_lower in author:
                return vip
        
        return None
    
    async def _handle_message(self, message):
        """Handle processed message from connector"""
        # This is called by individual connectors after they process messages
        pass
    
    async def _handle_error(self, error, context):
        """Handle error from connector"""
        logger.error(f"Connector error: {error} (context: {context})")
        
        for callback in self.error_callbacks:
            try:
                await callback(error, context)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")
    
    async def stop_monitoring(self, task_id: str) -> bool:
        """Stop specific monitoring task"""
        
        if task_id not in self.monitoring_tasks:
            logger.warning(f"Monitoring task {task_id} not found")
            return False
        
        try:
            # Cancel active stream
            if task_id in self.active_streams:
                stream_task = self.active_streams[task_id]
                stream_task.cancel()
                
                try:
                    await stream_task
                except asyncio.CancelledError:
                    pass
                
                del self.active_streams[task_id]
            
            # Remove task
            del self.monitoring_tasks[task_id]
            
            logger.info(f"Stopped monitoring task: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop monitoring task {task_id}: {e}")
            return False
    
    async def stop_all_monitoring(self):
        """Stop all monitoring tasks"""
        
        task_ids = list(self.monitoring_tasks.keys())
        
        for task_id in task_ids:
            await self.stop_monitoring(task_id)
        
        logger.info("All monitoring tasks stopped")
    
    async def shutdown(self):
        """Shutdown connector manager"""
        
        try:
            # Stop all monitoring
            await self.stop_all_monitoring()
            
            # Stop all connectors
            for platform, connector in self.connectors.items():
                try:
                    await connector.stop()
                    logger.info(f"Stopped {platform.value} connector")
                except Exception as e:
                    logger.error(f"Error stopping {platform.value} connector: {e}")
            
            self.connectors.clear()
            self.is_running = False
            self._stop_event.set()
            
            logger.info("Connector manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during connector manager shutdown: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all connectors and tasks"""
        
        connector_status = {}
        for platform, connector in self.connectors.items():
            connector_status[platform.value] = connector.get_metrics()
        
        task_status = {}
        for task_id, task in self.monitoring_tasks.items():
            task_status[task_id] = {
                'keywords': task.keywords,
                'vips': task.vips,
                'platforms': [p.value for p in task.platforms],
                'mode': task.mode.value,
                'duration': task.duration,
                'created_at': task.created_at.isoformat(),
                'active': task_id in self.active_streams
            }
        
        return {
            'manager_running': self.is_running,
            'active_connectors': len(self.connectors),
            'active_tasks': len(self.monitoring_tasks),
            'connectors': connector_status,
            'tasks': task_status
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all connectors"""
        
        health_results = {
            'manager_status': 'healthy' if self.is_running else 'stopped',
            'connectors': {},
            'overall_health': 'healthy'
        }
        
        unhealthy_count = 0
        
        for platform, connector in self.connectors.items():
            try:
                connector_health = await connector.health_check()
                health_results['connectors'][platform.value] = connector_health
                
                if connector_health['status'] != 'healthy':
                    unhealthy_count += 1
                    
            except Exception as e:
                health_results['connectors'][platform.value] = {
                    'status': 'error',
                    'error': str(e)
                }
                unhealthy_count += 1
        
        # Determine overall health
        if unhealthy_count == 0:
            health_results['overall_health'] = 'healthy'
        elif unhealthy_count < len(self.connectors):
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


# Global connector manager instance
connector_manager = SocialMediaConnectorManager()
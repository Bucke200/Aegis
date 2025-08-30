"""
Meta Graph API connector for Facebook and Instagram monitoring
"""
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable
from datetime import datetime, timedelta
import aiohttp
from .base_connector import BaseSocialMediaConnector, RateLimitInfo
from messaging.schemas import SourceType, Priority
from shared.config import settings
from shared.logging_config import logger


class MetaConnector(BaseSocialMediaConnector):
    """Meta Graph API connector for Facebook and Instagram"""
    
    def __init__(self, api_credentials: Dict[str, str], platform: str = 'facebook'):
        
        # Determine source type
        source_type = SourceType.FACEBOOK if platform.lower() == 'facebook' else SourceType.INSTAGRAM
        
        super().__init__(
            source_type=source_type,
            api_credentials=api_credentials,
            rate_limit_config={
                'graph_api': {'requests': 200, 'window': 3600},  # 200 per hour
                'search': {'requests': 5, 'window': 60}          # 5 per minute for search
            }
        )
        
        self.platform = platform.lower()
        self.base_url = 'https://graph.facebook.com/v18.0'
        self.access_token = api_credentials.get('access_token')
        
        # Platform-specific configurations
        if self.platform == 'instagram':
            self.instagram_business_account_id = api_credentials.get('instagram_business_account_id')
    
    async def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for Meta Graph API"""
        return {
            'User-Agent': 'Aegis-ThreatMonitor/1.0',
            'Accept': 'application/json'
        }
    
    async def _validate_credentials(self) -> bool:
        """Validate Meta API credentials"""
        try:
            # Test API access with a simple me request
            url = f"{self.base_url}/me"
            params = {
                'access_token': self.access_token,
                'fields': 'id,name'
            }
            
            response_data = await self._make_api_request(url, params=params)
            
            if 'id' in response_data:
                logger.info(f"Meta API authenticated for {self.platform}: {response_data.get('name', 'Unknown')}")
                return True
            else:
                logger.error("Meta API authentication failed")
                return False
                
        except Exception as e:
            logger.error(f"Meta credential validation failed: {e}")
            return False
    
    async def _setup_rate_limiting(self):
        """Setup Meta Graph API rate limiting"""
        self.rate_limit_info = RateLimitInfo(
            requests_remaining=200,
            reset_time=datetime.utcnow() + timedelta(hours=1),
            limit_window=3600,
            requests_per_window=200
        )
    
    async def search_posts(self, 
                          query: str, 
                          limit: int = 100,
                          since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search for posts matching query"""
        
        if self.platform == 'facebook':
            async for post in self._search_facebook_posts(query, limit, since):
                yield post
        elif self.platform == 'instagram':
            async for post in self._search_instagram_posts(query, limit, since):
                yield post
    
    async def _search_facebook_posts(self, 
                                    query: str, 
                                    limit: int,
                                    since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search Facebook posts (limited by API restrictions)"""
        
        # Note: Facebook Graph API has very limited public post search capabilities
        # This implementation focuses on pages and public content that can be accessed
        
        try:
            # Search for pages first
            pages = await self._search_facebook_pages(query)
            
            # Get posts from relevant pages
            for page in pages[:5]:  # Limit to top 5 pages
                page_id = page['id']
                
                async for post in self._get_facebook_page_posts(page_id, limit // 5, since):
                    if self._post_matches_query(post, query):
                        yield post
                        
        except Exception as e:
            logger.error(f"Facebook post search failed: {e}")
            raise
    
    async def _search_facebook_pages(self, query: str) -> List[Dict[str, Any]]:
        """Search for Facebook pages"""
        try:
            url = f"{self.base_url}/search"
            params = {
                'q': query,
                'type': 'page',
                'access_token': self.access_token,
                'fields': 'id,name,category,fan_count,verification_status',
                'limit': 10
            }
            
            response_data = await self._make_api_request(url, params=params)
            return response_data.get('data', [])
            
        except Exception as e:
            logger.error(f"Facebook page search failed: {e}")
            return []
    
    async def _get_facebook_page_posts(self, 
                                      page_id: str, 
                                      limit: int,
                                      since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from Facebook page"""
        try:
            url = f"{self.base_url}/{page_id}/posts"
            params = {
                'access_token': self.access_token,
                'fields': 'id,message,created_time,likes.summary(true),shares,comments.summary(true),from,permalink_url',
                'limit': min(limit, 25)  # Facebook API limit
            }
            
            if since:
                params['since'] = int(since.timestamp())
            
            response_data = await self._make_api_request(url, params=params)
            posts = response_data.get('data', [])
            
            for post in posts:
                try:
                    post_data = self._convert_facebook_post(post)
                    yield post_data
                except Exception as e:
                    logger.error(f"Error converting Facebook post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get Facebook page posts: {e}")
            raise
    
    async def _search_instagram_posts(self, 
                                     query: str, 
                                     limit: int,
                                     since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search Instagram posts using hashtag and location search"""
        
        if not self.instagram_business_account_id:
            logger.error("Instagram Business Account ID required for Instagram search")
            return
        
        try:
            # Search by hashtag
            hashtag_posts = await self._search_instagram_hashtag(query, limit // 2, since)
            for post in hashtag_posts:
                yield post
            
            # Search recent media from business account
            async for post in self._get_instagram_user_posts(
                self.instagram_business_account_id, 
                limit // 2, 
                since
            ):
                if self._post_matches_query(post, query):
                    yield post
                    
        except Exception as e:
            logger.error(f"Instagram post search failed: {e}")
            raise
    
    async def _search_instagram_hashtag(self, 
                                       hashtag: str, 
                                       limit: int,
                                       since: Optional[datetime]) -> List[Dict[str, Any]]:
        """Search Instagram posts by hashtag"""
        try:
            # First, get hashtag ID
            hashtag_search_url = f"{self.base_url}/ig_hashtag_search"
            hashtag_params = {
                'user_id': self.instagram_business_account_id,
                'q': hashtag.replace('#', ''),
                'access_token': self.access_token
            }
            
            hashtag_response = await self._make_api_request(hashtag_search_url, params=hashtag_params)
            hashtag_data = hashtag_response.get('data', [])
            
            if not hashtag_data:
                return []
            
            hashtag_id = hashtag_data[0]['id']
            
            # Get recent media for hashtag
            media_url = f"{self.base_url}/{hashtag_id}/recent_media"
            media_params = {
                'user_id': self.instagram_business_account_id,
                'access_token': self.access_token,
                'fields': 'id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count',
                'limit': min(limit, 25)
            }
            
            media_response = await self._make_api_request(media_url, params=media_params)
            posts = media_response.get('data', [])
            
            converted_posts = []
            for post in posts:
                try:
                    # Filter by date if specified
                    if since:
                        post_time = datetime.fromisoformat(post['timestamp'].replace('Z', '+00:00'))
                        if post_time < since:
                            continue
                    
                    post_data = self._convert_instagram_post(post)
                    converted_posts.append(post_data)
                except Exception as e:
                    logger.error(f"Error converting Instagram post: {e}")
                    continue
            
            return converted_posts
            
        except Exception as e:
            logger.error(f"Instagram hashtag search failed: {e}")
            return []
    
    async def get_user_posts(self, 
                            user_id: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from specific user"""
        
        if self.platform == 'facebook':
            async for post in self._get_facebook_page_posts(user_id, limit, since):
                yield post
        elif self.platform == 'instagram':
            async for post in self._get_instagram_user_posts(user_id, limit, since):
                yield post
    
    async def _get_instagram_user_posts(self, 
                                       user_id: str, 
                                       limit: int,
                                       since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Get Instagram posts from user"""
        try:
            url = f"{self.base_url}/{user_id}/media"
            params = {
                'access_token': self.access_token,
                'fields': 'id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count,owner',
                'limit': min(limit, 25)
            }
            
            if since:
                params['since'] = int(since.timestamp())
            
            response_data = await self._make_api_request(url, params=params)
            posts = response_data.get('data', [])
            
            for post in posts:
                try:
                    post_data = self._convert_instagram_post(post)
                    yield post_data
                except Exception as e:
                    logger.error(f"Error converting Instagram user post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get Instagram user posts: {e}")
            raise
    
    async def stream_real_time(self, 
                              keywords: List[str],
                              callback: Callable) -> None:
        """Stream real-time posts (polling-based for Meta APIs)"""
        
        logger.info(f"Starting Meta {self.platform} polling for keywords: {keywords}")
        
        try:
            while not self._stop_event.is_set():
                for keyword in keywords:
                    try:
                        # Search for recent posts
                        async for post_data in self.search_posts(
                            query=keyword, 
                            limit=10,
                            since=datetime.utcnow() - timedelta(minutes=5)
                        ):
                            await callback(post_data)
                    
                    except Exception as e:
                        logger.error(f"Error in Meta polling for keyword '{keyword}': {e}")
                
                # Wait before next poll (respect rate limits)
                await asyncio.sleep(60)  # Poll every minute
                
        except Exception as e:
            logger.error(f"Meta streaming failed: {e}")
            raise
    
    def _convert_facebook_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Facebook post to standardized format"""
        
        # Extract basic information
        post_data = {
            'post_id': post['id'],
            'author_id': post.get('from', {}).get('id', 'unknown'),
            'author_username': post.get('from', {}).get('name', 'unknown'),
            'author_display_name': post.get('from', {}).get('name', 'unknown'),
            'content': post.get('message', ''),
            'created_at': datetime.fromisoformat(post['created_time'].replace('Z', '+00:00')),
            'url': post.get('permalink_url', ''),
            'content_type': 'text'
        }
        
        # Extract engagement metrics
        likes_data = post.get('likes', {})
        if isinstance(likes_data, dict) and 'summary' in likes_data:
            post_data['likes'] = likes_data['summary'].get('total_count', 0)
        
        shares_data = post.get('shares', {})
        if isinstance(shares_data, dict):
            post_data['shares'] = shares_data.get('count', 0)
        
        comments_data = post.get('comments', {})
        if isinstance(comments_data, dict) and 'summary' in comments_data:
            post_data['comments'] = comments_data['summary'].get('total_count', 0)
        
        return post_data
    
    def _convert_instagram_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Instagram post to standardized format"""
        
        # Extract basic information
        post_data = {
            'post_id': post['id'],
            'author_id': post.get('owner', {}).get('id', 'unknown') if 'owner' in post else 'unknown',
            'author_username': 'instagram_user',  # Instagram API doesn't provide username in basic access
            'author_display_name': 'Instagram User',
            'content': post.get('caption', ''),
            'created_at': datetime.fromisoformat(post['timestamp'].replace('Z', '+00:00')),
            'url': post.get('permalink', ''),
            'content_type': post.get('media_type', 'image').lower()
        }
        
        # Extract engagement metrics
        post_data['likes'] = post.get('like_count', 0)
        post_data['comments'] = post.get('comments_count', 0)
        post_data['shares'] = 0  # Instagram doesn't provide share count
        
        # Add media URL if available
        if 'media_url' in post:
            post_data['media_urls'] = [post['media_url']]
        
        return post_data
    
    def _post_matches_query(self, post_data: Dict[str, Any], query: str) -> bool:
        """Check if post matches search query"""
        content = post_data.get('content', '').lower()
        query_lower = query.lower()
        
        return query_lower in content
    
    async def _update_rate_limit_info(self, response: aiohttp.ClientResponse):
        """Update rate limit info from Meta API response"""
        try:
            # Meta uses different headers for rate limiting
            usage_header = response.headers.get('x-app-usage')
            if usage_header:
                import json
                usage_data = json.loads(usage_header)
                
                # Extract call count percentage
                call_count = usage_data.get('call_count', 0)
                
                # Estimate remaining requests (Meta uses percentage)
                remaining = max(0, 100 - call_count)
                
                self.rate_limit_info = RateLimitInfo(
                    requests_remaining=remaining,
                    reset_time=datetime.utcnow() + timedelta(hours=1),
                    limit_window=3600,
                    requests_per_window=200
                )
                
        except Exception as e:
            logger.error(f"Failed to update Meta rate limit info: {e}")
    
    async def _extract_rate_limit_wait_time(self, response: aiohttp.ClientResponse) -> Optional[int]:
        """Extract rate limit wait time from Meta response"""
        # Meta API typically returns 429 with retry-after header
        retry_after = response.headers.get('retry-after')
        if retry_after:
            return int(retry_after)
        
        return 3600  # Default 1 hour for Meta API
    
    async def get_page_info(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed page information"""
        try:
            url = f"{self.base_url}/{page_id}"
            params = {
                'access_token': self.access_token,
                'fields': 'id,name,category,fan_count,verification_status,about,website,location'
            }
            
            response_data = await self._make_api_request(url, params=params)
            
            return {
                'page_id': response_data.get('id'),
                'name': response_data.get('name'),
                'category': response_data.get('category'),
                'fan_count': response_data.get('fan_count', 0),
                'verified': response_data.get('verification_status') == 'blue_verified',
                'about': response_data.get('about', ''),
                'website': response_data.get('website', ''),
                'location': response_data.get('location', {})
            }
            
        except Exception as e:
            logger.error(f"Failed to get page info for {page_id}: {e}")
            return None


# Factory functions for easy initialization
def create_facebook_connector() -> MetaConnector:
    """Create Facebook connector with configuration from settings"""
    
    credentials = {
        'access_token': settings.facebook_access_token
    }
    
    if not credentials['access_token']:
        raise ValueError("Facebook access token is required")
    
    return MetaConnector(credentials, platform='facebook')


def create_instagram_connector() -> MetaConnector:
    """Create Instagram connector with configuration from settings"""
    
    credentials = {
        'access_token': settings.facebook_access_token,  # Same token for Instagram Business API
        'instagram_business_account_id': settings.instagram_business_account_id
    }
    
    if not credentials['access_token']:
        raise ValueError("Facebook access token is required for Instagram API")
    
    if not credentials['instagram_business_account_id']:
        raise ValueError("Instagram Business Account ID is required")
    
    return MetaConnector(credentials, platform='instagram')
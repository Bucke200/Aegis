"""
LinkedIn API connector for professional network monitoring
"""
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable
from datetime import datetime, timedelta
import aiohttp
from .base_connector import BaseSocialMediaConnector, RateLimitInfo
from messaging.schemas import SourceType, Priority
from shared.config import settings
from shared.logging_config import logger


class LinkedInConnector(BaseSocialMediaConnector):
    """LinkedIn API connector for professional network monitoring"""
    
    def __init__(self, api_credentials: Dict[str, str]):
        super().__init__(
            source_type=SourceType.LINKEDIN,
            api_credentials=api_credentials,
            rate_limit_config={
                'api_calls': {'requests': 500, 'window': 86400},  # 500 per day
                'search': {'requests': 100, 'window': 86400}      # 100 searches per day
            }
        )
        
        self.base_url = 'https://api.linkedin.com/v2'
        self.access_token = api_credentials.get('access_token')
        
        # LinkedIn API has limited public content access
        # Most functionality requires user consent or company page access
        self.organization_id = api_credentials.get('organization_id')
    
    async def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for LinkedIn API"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': 'Aegis-ThreatMonitor/1.0',
            'Accept': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }
    
    async def _validate_credentials(self) -> bool:
        """Validate LinkedIn API credentials"""
        try:
            # Test API access with profile request
            url = f"{self.base_url}/people/~"
            params = {
                'projection': '(id,firstName,lastName)'
            }
            
            response_data = await self._make_api_request(url, params=params)
            
            if 'id' in response_data:
                name = f"{response_data.get('firstName', {}).get('localized', {}).get('en_US', 'Unknown')} {response_data.get('lastName', {}).get('localized', {}).get('en_US', '')}"
                logger.info(f"LinkedIn API authenticated: {name}")
                return True
            else:
                logger.error("LinkedIn API authentication failed")
                return False
                
        except Exception as e:
            logger.error(f"LinkedIn credential validation failed: {e}")
            return False
    
    async def _setup_rate_limiting(self):
        """Setup LinkedIn API rate limiting"""
        self.rate_limit_info = RateLimitInfo(
            requests_remaining=500,
            reset_time=datetime.utcnow() + timedelta(days=1),
            limit_window=86400,
            requests_per_window=500
        )
    
    async def search_posts(self, 
                          query: str, 
                          limit: int = 100,
                          since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search LinkedIn posts (limited by API restrictions)"""
        
        # LinkedIn API has very limited public post search
        # This implementation focuses on organization posts and user-authorized content
        
        try:
            # Search organization posts if organization ID is available
            if self.organization_id:
                async for post in self._get_organization_posts(
                    self.organization_id, 
                    limit, 
                    since
                ):
                    if self._post_matches_query(post, query):
                        yield post
            
            # Search user's network posts (requires user authorization)
            async for post in self._search_network_posts(query, limit, since):
                yield post
                
        except Exception as e:
            logger.error(f"LinkedIn post search failed: {e}")
            raise
    
    async def _search_network_posts(self, 
                                   query: str, 
                                   limit: int,
                                   since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search posts in user's network"""
        
        # Note: This requires specific permissions and user consent
        # LinkedIn API doesn't provide general public post search
        
        try:
            url = f"{self.base_url}/shares"
            params = {
                'q': 'owners',
                'owners': 'urn:li:person:~',  # Current user's posts
                'projection': '(elements*(id,text,content,created,owner,distribution))',
                'count': min(limit, 50)
            }
            
            if since:
                # LinkedIn uses milliseconds timestamp
                params['created.after'] = int(since.timestamp() * 1000)
            
            response_data = await self._make_api_request(url, params=params)
            posts = response_data.get('elements', [])
            
            for post in posts:
                try:
                    post_data = self._convert_linkedin_post(post)
                    if self._post_matches_query(post_data, query):
                        yield post_data
                except Exception as e:
                    logger.error(f"Error converting LinkedIn post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"LinkedIn network search failed: {e}")
            # Don't raise here as this might be due to permissions
            pass
    
    async def get_user_posts(self, 
                            user_id: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from specific LinkedIn user/organization"""
        
        try:
            # Determine if this is a person or organization
            if user_id.startswith('urn:li:organization:') or self.organization_id:
                # Organization posts
                org_id = user_id if user_id.startswith('urn:li:organization:') else self.organization_id
                async for post in self._get_organization_posts(org_id, limit, since):
                    yield post
            else:
                # Person posts (requires authorization)
                async for post in self._get_person_posts(user_id, limit, since):
                    yield post
                    
        except Exception as e:
            logger.error(f"Failed to get LinkedIn user posts: {e}")
            raise
    
    async def _get_organization_posts(self, 
                                     org_id: str, 
                                     limit: int,
                                     since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from LinkedIn organization"""
        
        try:
            url = f"{self.base_url}/shares"
            params = {
                'q': 'owners',
                'owners': org_id if org_id.startswith('urn:li:organization:') else f'urn:li:organization:{org_id}',
                'projection': '(elements*(id,text,content,created,owner,distribution,activity))',
                'count': min(limit, 50)
            }
            
            if since:
                params['created.after'] = int(since.timestamp() * 1000)
            
            response_data = await self._make_api_request(url, params=params)
            posts = response_data.get('elements', [])
            
            for post in posts:
                try:
                    post_data = self._convert_linkedin_post(post)
                    yield post_data
                except Exception as e:
                    logger.error(f"Error converting LinkedIn organization post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get LinkedIn organization posts: {e}")
            raise
    
    async def _get_person_posts(self, 
                               person_id: str, 
                               limit: int,
                               since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from LinkedIn person (requires authorization)"""
        
        try:
            url = f"{self.base_url}/shares"
            params = {
                'q': 'owners',
                'owners': person_id if person_id.startswith('urn:li:person:') else f'urn:li:person:{person_id}',
                'projection': '(elements*(id,text,content,created,owner,distribution))',
                'count': min(limit, 50)
            }
            
            if since:
                params['created.after'] = int(since.timestamp() * 1000)
            
            response_data = await self._make_api_request(url, params=params)
            posts = response_data.get('elements', [])
            
            for post in posts:
                try:
                    post_data = self._convert_linkedin_post(post)
                    yield post_data
                except Exception as e:
                    logger.error(f"Error converting LinkedIn person post: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get LinkedIn person posts: {e}")
            # Don't raise as this might be due to privacy settings
            pass
    
    async def stream_real_time(self, 
                              keywords: List[str],
                              callback: Callable) -> None:
        """Stream real-time posts (polling-based for LinkedIn)"""
        
        logger.info(f"Starting LinkedIn polling for keywords: {keywords}")
        
        try:
            last_check = datetime.utcnow()
            
            while not self._stop_event.is_set():
                current_time = datetime.utcnow()
                
                for keyword in keywords:
                    try:
                        # Search for recent posts
                        async for post_data in self.search_posts(
                            query=keyword, 
                            limit=10,
                            since=last_check
                        ):
                            await callback(post_data)
                    
                    except Exception as e:
                        logger.error(f"Error in LinkedIn polling for keyword '{keyword}': {e}")
                
                last_check = current_time
                
                # Wait before next poll (respect rate limits - LinkedIn has daily limits)
                await asyncio.sleep(300)  # Poll every 5 minutes
                
        except Exception as e:
            logger.error(f"LinkedIn streaming failed: {e}")
            raise
    
    def _convert_linkedin_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Convert LinkedIn post to standardized format"""
        
        # Extract basic information
        post_data = {
            'post_id': post.get('id', ''),
            'author_id': self._extract_author_id(post),
            'author_username': 'linkedin_user',  # LinkedIn doesn't provide username in API
            'author_display_name': self._extract_author_name(post),
            'content': self._extract_post_text(post),
            'created_at': self._convert_linkedin_timestamp(post.get('created', {})),
            'url': self._generate_linkedin_url(post),
            'content_type': 'text'
        }
        
        # Extract engagement metrics if available
        activity = post.get('activity', {})
        if activity:
            post_data.update({
                'likes': activity.get('likes', {}).get('totalCount', 0),
                'comments': activity.get('comments', {}).get('totalCount', 0),
                'shares': activity.get('shares', {}).get('totalCount', 0)
            })
        
        # Extract content media if available
        content = post.get('content', {})
        if content and 'media' in content:
            media_urls = []
            for media in content.get('media', []):
                if 'originalUrl' in media:
                    media_urls.append(media['originalUrl'])
            post_data['media_urls'] = media_urls
        
        return post_data
    
    def _extract_author_id(self, post: Dict[str, Any]) -> str:
        """Extract author ID from LinkedIn post"""
        owner = post.get('owner', '')
        if isinstance(owner, str):
            return owner
        elif isinstance(owner, dict):
            return owner.get('id', 'unknown')
        return 'unknown'
    
    def _extract_author_name(self, post: Dict[str, Any]) -> str:
        """Extract author name from LinkedIn post"""
        # LinkedIn API structure varies, try different paths
        owner = post.get('owner', {})
        
        if isinstance(owner, dict):
            # Try to get name from owner object
            if 'name' in owner:
                return owner['name']
            elif 'localizedName' in owner:
                return owner['localizedName']
        
        return 'LinkedIn User'
    
    def _extract_post_text(self, post: Dict[str, Any]) -> str:
        """Extract text content from LinkedIn post"""
        # Try different text fields
        if 'text' in post:
            text_obj = post['text']
            if isinstance(text_obj, dict):
                # Handle localized text
                if 'text' in text_obj:
                    return text_obj['text']
                elif 'localized' in text_obj:
                    localized = text_obj['localized']
                    # Try to get English text first
                    return localized.get('en_US', list(localized.values())[0] if localized else '')
            elif isinstance(text_obj, str):
                return text_obj
        
        # Try content field
        content = post.get('content', {})
        if 'description' in content:
            return content['description']
        
        return ''
    
    def _convert_linkedin_timestamp(self, timestamp_obj: Dict[str, Any]) -> datetime:
        """Convert LinkedIn timestamp to datetime"""
        if isinstance(timestamp_obj, dict) and 'time' in timestamp_obj:
            # LinkedIn uses milliseconds
            timestamp_ms = timestamp_obj['time']
            return datetime.fromtimestamp(timestamp_ms / 1000)
        elif isinstance(timestamp_obj, (int, float)):
            return datetime.fromtimestamp(timestamp_obj / 1000)
        else:
            return datetime.utcnow()
    
    def _generate_linkedin_url(self, post: Dict[str, Any]) -> str:
        """Generate LinkedIn post URL"""
        post_id = post.get('id', '')
        if post_id:
            # Extract activity ID from URN if possible
            if 'activity:' in post_id:
                activity_id = post_id.split('activity:')[-1].rstrip(')')
                return f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"
        
        return "https://www.linkedin.com"
    
    def _post_matches_query(self, post_data: Dict[str, Any], query: str) -> bool:
        """Check if post matches search query"""
        content = post_data.get('content', '').lower()
        author_name = post_data.get('author_display_name', '').lower()
        query_lower = query.lower()
        
        return query_lower in content or query_lower in author_name
    
    async def _update_rate_limit_info(self, response: aiohttp.ClientResponse):
        """Update rate limit info from LinkedIn API response"""
        try:
            # LinkedIn uses X-RateLimit headers
            remaining = response.headers.get('X-RateLimit-Remaining')
            reset_time = response.headers.get('X-RateLimit-Reset')
            
            if remaining:
                self.rate_limit_info = RateLimitInfo(
                    requests_remaining=int(remaining),
                    reset_time=datetime.fromtimestamp(int(reset_time)) if reset_time else datetime.utcnow() + timedelta(days=1),
                    limit_window=86400,  # 24 hours
                    requests_per_window=500
                )
                
        except Exception as e:
            logger.error(f"Failed to update LinkedIn rate limit info: {e}")
    
    async def _extract_rate_limit_wait_time(self, response: aiohttp.ClientResponse) -> Optional[int]:
        """Extract rate limit wait time from LinkedIn response"""
        try:
            reset_time = response.headers.get('X-RateLimit-Reset')
            if reset_time:
                wait_time = int(reset_time) - int(datetime.utcnow().timestamp())
                return max(wait_time, 300)  # At least 5 minutes
        except Exception:
            pass
        
        return 3600  # Default 1 hour for LinkedIn
    
    async def get_organization_info(self, org_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed organization information"""
        try:
            url = f"{self.base_url}/organizations/{org_id}"
            params = {
                'projection': '(id,name,description,website,industry,employeeCountRange,foundedOn,locations)'
            }
            
            response_data = await self._make_api_request(url, params=params)
            
            return {
                'organization_id': response_data.get('id'),
                'name': response_data.get('name', {}).get('localized', {}).get('en_US', 'Unknown'),
                'description': response_data.get('description', {}).get('localized', {}).get('en_US', ''),
                'website': response_data.get('website', ''),
                'industry': response_data.get('industry', ''),
                'employee_count': response_data.get('employeeCountRange', {}),
                'founded_on': response_data.get('foundedOn', {}),
                'locations': response_data.get('locations', [])
            }
            
        except Exception as e:
            logger.error(f"Failed to get organization info for {org_id}: {e}")
            return None
    
    async def search_companies(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for companies on LinkedIn"""
        try:
            url = f"{self.base_url}/organizationSearch"
            params = {
                'q': 'keywords',
                'keywords': query,
                'projection': '(elements*(id,name,description,website,industry))',
                'count': min(limit, 50)
            }
            
            response_data = await self._make_api_request(url, params=params)
            organizations = response_data.get('elements', [])
            
            results = []
            for org in organizations:
                try:
                    org_data = {
                        'id': org.get('id'),
                        'name': org.get('name', {}).get('localized', {}).get('en_US', 'Unknown'),
                        'description': org.get('description', {}).get('localized', {}).get('en_US', ''),
                        'website': org.get('website', ''),
                        'industry': org.get('industry', '')
                    }
                    results.append(org_data)
                except Exception as e:
                    logger.error(f"Error processing organization data: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"LinkedIn company search failed: {e}")
            return []


# Factory function for easy initialization
def create_linkedin_connector() -> LinkedInConnector:
    """Create LinkedIn connector with configuration from settings"""
    
    credentials = {
        'access_token': settings.linkedin_access_token,
        'organization_id': settings.linkedin_organization_id
    }
    
    if not credentials['access_token']:
        raise ValueError("LinkedIn access token is required")
    
    return LinkedInConnector(credentials)
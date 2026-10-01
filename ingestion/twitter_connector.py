"""
Twitter/X API connector for real-time threat monitoring
"""
import asyncio
import json
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable
from datetime import datetime, timedelta
import aiohttp
import tweepy
from tweepy.asynchronous import AsyncClient, AsyncStreamingClient
from .base_connector import BaseSocialMediaConnector, RateLimitInfo
from messaging.schemas import SourceType, Priority
from shared.config import settings
from shared.logging_config import logger


def _convert_tweet_data(tweet) -> Dict[str, Any]:
    """Convert Twitter tweet to standardized format"""
    
    # Handle different tweet object types
    if hasattr(tweet, 'data'):
        tweet_data = tweet.data
    else:
        tweet_data = tweet
    
    # Extract basic information
    post_data = {
        'post_id': str(tweet_data.id),
        'author_id': str(tweet_data.author_id) if hasattr(tweet_data, 'author_id') else 'unknown',
        'author_username': getattr(tweet_data, 'username', 'unknown'),
        'author_display_name': getattr(tweet_data, 'name', 'unknown'),
        'content': tweet_data.text,
        'created_at': tweet_data.created_at or datetime.utcnow(),
        'url': f"https://twitter.com/i/status/{tweet_data.id}",
        'language': getattr(tweet_data, 'lang', None)
    }
    
    # Extract metrics if available
    if hasattr(tweet_data, 'public_metrics'):
        metrics = tweet_data.public_metrics
        post_data.update({
            'likes': metrics.get('like_count', 0),
            'shares': metrics.get('retweet_count', 0),
            'comments': metrics.get('reply_count', 0),
            'views': metrics.get('impression_count', 0)
        })
    
    # Extract entities
    if hasattr(tweet_data, 'entities'):
        entities = tweet_data.entities
        
        # Hashtags
        if 'hashtags' in entities:
            post_data['hashtags'] = [tag['tag'] for tag in entities['hashtags']]
        
        # Mentions
        if 'mentions' in entities:
            post_data['mentions'] = [mention['username'] for mention in entities['mentions']]
        
        # URLs
        if 'urls' in entities:
            post_data['media_urls'] = [url['expanded_url'] for url in entities['urls']]
    
    # Extract author information if available
    if hasattr(tweet, 'includes') and tweet.includes and 'users' in tweet.includes:
        for user in tweet.includes['users']:
            if str(user.id) == post_data['author_id']:
                post_data.update({
                    'author_username': user.username,
                    'author_display_name': user.name,
                    'author_followers': getattr(user, 'public_metrics', {}).get('followers_count', 0),
                    'author_verified': getattr(user, 'verified', False),
                    'author_created_at': getattr(user, 'created_at', None)
                })
                break
    
    # Extract location if available
    if hasattr(tweet_data, 'geo') and tweet_data.geo:
        post_data['location'] = str(tweet_data.geo)
    
    return post_data


class TwitterStreamListener(tweepy.asynchronous.AsyncStreamingClient):
    """Custom Twitter streaming client"""
    
    def __init__(self, bearer_token: str, callback: Callable):
        super().__init__(bearer_token)
        self.callback = callback
        self.is_running = False
    
    async def on_tweet(self, tweet):
        """Handle incoming tweet"""
        try:
            if not self.is_running:
                return
            
            # Convert tweet to our format
            tweet_data = _convert_tweet_data(tweet)
            
            # Call the callback
            await self.callback(tweet_data)
            
        except Exception as e:
            logger.error(f"Error processing tweet: {e}")
    
    async def on_error(self, status_code):
        """Handle streaming errors"""
        logger.error(f"Twitter streaming error: {status_code}")
        if status_code == 420:  # Rate limited
            logger.warning("Twitter streaming rate limited")
            return False  # Disconnect
        return True  # Continue


class TwitterConnector(BaseSocialMediaConnector):
    """Twitter/X API connector"""
    
    def __init__(self, api_credentials: Dict[str, str]):
        super().__init__(
            source_type=SourceType.TWITTER,
            api_credentials=api_credentials,
            rate_limit_config={
                'search_tweets': {'requests': 300, 'window': 900},  # 300 per 15 min
                'user_tweets': {'requests': 900, 'window': 900},    # 900 per 15 min
                'streaming': {'connections': 1}                      # 1 concurrent stream
            }
        )
        
        # Twitter API clients
        self.client: Optional[AsyncClient] = None
        self.streaming_client: Optional[TwitterStreamListener] = None
        
        # Rate limiting
        self.rate_limits = {}
    
    async def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for Twitter API"""
        return {
            'User-Agent': 'Aegis-ThreatMonitor/1.0',
            'Accept': 'application/json'
        }
    
    async def _validate_credentials(self) -> bool:
        """Validate Twitter API credentials"""
        try:
            if not self.client:
                await self._initialize_clients()
            
            # Test API access with a simple search (works with Bearer Token)
            await self.client.search_recent_tweets(
                query="hello",
                max_results=10
            )
            
            logger.info("Twitter API Bearer Token validated successfully")
            return True
                
        except Exception as e:
            logger.error(f"Twitter credential validation failed: {e}")
            return False
    
    async def _initialize_clients(self):
        """Initialize Twitter API clients"""
        try:
            bearer_token = self.api_credentials.get('bearer_token')
            if not bearer_token:
                raise ValueError("Twitter bearer token is required")
            
            # Initialize async client
            self.client = AsyncClient(
                bearer_token=bearer_token,
                wait_on_rate_limit=True
            )
            
            logger.info("Twitter API clients initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Twitter clients: {e}")
            raise
    
    async def _setup_rate_limiting(self):
        """Setup Twitter rate limiting"""
        # Initialize rate limit tracking
        self.rate_limits = {
            'search_tweets': {
                'remaining': 300,
                'reset_time': datetime.utcnow() + timedelta(minutes=15)
            },
            'user_tweets': {
                'remaining': 900,
                'reset_time': datetime.utcnow() + timedelta(minutes=15)
            }
        }
    
    async def search_posts(self, 
                          query: str, 
                          limit: int = 100,
                          since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search Twitter for posts matching query"""
        
        if not self.client:
            await self._initialize_clients()
        
        try:
            # Prepare search parameters
            search_params = {
                'query': query,
                'max_results': max(10, min(limit, 100)),  # Twitter API allows 10-100
                'tweet.fields': [
                    'created_at', 'author_id', 'public_metrics', 
                    'entities', 'geo', 'lang', 'context_annotations'
                ],
                'user.fields': [
                    'username', 'name', 'verified', 'public_metrics', 'created_at'
                ],
                'expansions': ['author_id']
            }
            
            if since:
                search_params['start_time'] = since.isoformat()
            
            # Perform search
            tweets = await self.client.search_recent_tweets(**search_params)
            
            if not tweets.data:
                logger.info(f"No tweets found for query: {query}")
                return
            
            # Process tweets
            for tweet in tweets.data:
                try:
                    # Create tweet object with includes
                    tweet_with_includes = type('Tweet', (), {
                        'data': tweet,
                        'includes': tweets.includes or {}
                    })()
                    
                    # Convert to standardized format
                    tweet_data = _convert_tweet_data(tweet_with_includes)
                    
                    yield tweet_data
                    
                except Exception as e:
                    logger.error(f"Error processing tweet {tweet.id}: {e}")
                    continue
            
            # Handle pagination if needed
            if hasattr(tweets, 'meta') and 'next_token' in tweets.meta:
                # Could implement pagination here for larger result sets
                pass
                
        except Exception as e:
            logger.error(f"Twitter search failed: {e}")
            raise
    
    async def get_user_posts(self, 
                            user_id: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Get posts from specific Twitter user"""
        
        if not self.client:
            await self._initialize_clients()
        
        try:
            # Prepare parameters
            params = {
                'id': user_id,
                'max_results': max(10, min(limit, 100)),
                'tweet.fields': [
                    'created_at', 'public_metrics', 'entities', 
                    'geo', 'lang', 'context_annotations'
                ],
                'user.fields': [
                    'username', 'name', 'verified', 'public_metrics'
                ]
            }
            
            if since:
                params['start_time'] = since.isoformat()
            
            # Get user tweets
            tweets = await self.client.get_users_tweets(**params)
            
            if not tweets.data:
                logger.info(f"No tweets found for user: {user_id}")
                return
            
            # Get user info
            user_info = await self.client.get_user(id=user_id, user_fields=['username', 'name', 'verified', 'public_metrics'])
            
            # Process tweets
            for tweet in tweets.data:
                try:
                    # Create tweet object with user info
                    tweet_with_user = type('Tweet', (), {
                        'data': tweet,
                        'includes': {'users': [user_info.data]} if user_info.data else {}
                    })()
                    
                    # Convert to standardized format
                    tweet_data = _convert_tweet_data(tweet_with_user)
                    
                    yield tweet_data
                    
                except Exception as e:
                    logger.error(f"Error processing user tweet {tweet.id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to get user posts: {e}")
            raise
    
    async def stream_real_time(self, 
                              keywords: List[str],
                              callback: Callable) -> None:
        """Stream real-time tweets matching keywords"""
        
        try:
            bearer_token = self.api_credentials.get('bearer_token')
            if not bearer_token:
                raise ValueError("Bearer token required for streaming")
            
            # Create streaming client
            self.streaming_client = TwitterStreamListener(bearer_token, callback)
            
            # Clear existing rules
            rules = await self.streaming_client.get_rules()
            if rules.data:
                rule_ids = [rule.id for rule in rules.data]
                await self.streaming_client.delete_rules(rule_ids)
            
            # Add new rules for keywords
            new_rules = []
            for keyword in keywords:
                # Create rule for keyword (can be enhanced with operators)
                rule_value = f'"{keyword}" -is:retweet lang:en'
                new_rules.append(tweepy.StreamRule(rule_value, tag=f"keyword_{keyword}"))
            
            if new_rules:
                await self.streaming_client.add_rules(new_rules)
            
            # Start streaming
            logger.info(f"Starting Twitter stream for keywords: {keywords}")
            self.streaming_client.is_running = True
            
            await self.streaming_client.filter(
                tweet_fields=[
                    'created_at', 'author_id', 'public_metrics', 
                    'entities', 'geo', 'lang'
                ],
                user_fields=[
                    'username', 'name', 'verified', 'public_metrics'
                ],
                expansions=['author_id']
            )
            
        except Exception as e:
            logger.error(f"Twitter streaming failed: {e}")
            if self.streaming_client:
                self.streaming_client.is_running = False
            raise
    
    async def stop_streaming(self):
        """Stop real-time streaming"""
        if self.streaming_client:
            self.streaming_client.is_running = False
            await self.streaming_client.disconnect()
            logger.info("Twitter streaming stopped")
    
    async def _update_rate_limit_info(self, response: aiohttp.ClientResponse):
        """Update rate limit info from Twitter API response"""
        try:
            remaining = response.headers.get('x-rate-limit-remaining')
            reset_time = response.headers.get('x-rate-limit-reset')
            
            if remaining and reset_time:
                self.rate_limit_info = RateLimitInfo(
                    requests_remaining=int(remaining),
                    reset_time=datetime.fromtimestamp(int(reset_time)),
                    limit_window=900,  # 15 minutes
                    requests_per_window=300  # Default for search
                )
                
        except Exception as e:
            logger.error(f"Failed to update Twitter rate limit info: {e}")
    
    async def _extract_rate_limit_wait_time(self, response: aiohttp.ClientResponse) -> Optional[int]:
        """Extract rate limit wait time from Twitter response"""
        try:
            reset_time = response.headers.get('x-rate-limit-reset')
            if reset_time:
                wait_time = int(reset_time) - int(datetime.utcnow().timestamp())
                return max(wait_time, 60)  # At least 1 minute
        except Exception:
            pass
        
        return 900  # Default 15 minutes for Twitter
    
    async def monitor_user_mentions(self, username: str, callback: Callable):
        """Monitor mentions of a specific user"""
        query = f"@{username} OR \"{username}\""
        
        try:
            async for tweet_data in self.search_posts(query, limit=100):
                await callback(tweet_data)
                
        except Exception as e:
            logger.error(f"Failed to monitor user mentions: {e}")
            raise
    
    async def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get detailed user information"""
        try:
            if not self.client:
                await self._initialize_clients()
            
            user = await self.client.get_user(
                username=username,
                user_fields=[
                    'created_at', 'description', 'public_metrics', 
                    'verified', 'profile_image_url', 'location'
                ]
            )
            
            if user.data:
                return {
                    'user_id': str(user.data.id),
                    'username': user.data.username,
                    'display_name': user.data.name,
                    'description': getattr(user.data, 'description', ''),
                    'followers_count': getattr(user.data, 'public_metrics', {}).get('followers_count', 0),
                    'following_count': getattr(user.data, 'public_metrics', {}).get('following_count', 0),
                    'tweet_count': getattr(user.data, 'public_metrics', {}).get('tweet_count', 0),
                    'verified': getattr(user.data, 'verified', False),
                    'created_at': getattr(user.data, 'created_at', None),
                    'profile_image_url': getattr(user.data, 'profile_image_url', ''),
                    'location': getattr(user.data, 'location', '')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user info for {username}: {e}")
            return None


# Factory function for easy initialization
def create_twitter_connector() -> TwitterConnector:
    """Create Twitter connector with configuration from settings"""
    
    credentials = {
        'bearer_token': settings.twitter_bearer_token,
        'api_key': settings.twitter_api_key,
        'api_secret': settings.twitter_api_secret,
        'access_token': settings.twitter_access_token,
        'access_token_secret': settings.twitter_access_token_secret
    }
    
    # Validate required credentials
    if not credentials['bearer_token']:
        raise ValueError("Twitter bearer token is required")
    
    return TwitterConnector(credentials)
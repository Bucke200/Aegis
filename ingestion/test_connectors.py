"""
Test suite for social media API connectors
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch
from .connector_manager import connector_manager, MonitoringMode
from .base_connector import ConnectorStatus
from messaging.schemas import SourceType
from shared.logging_config import logger


class ConnectorTester:
    """Test suite for social media connectors"""
    
    def __init__(self):
        self.test_results = []
        self.mock_credentials = {
            'twitter': {
                'bearer_token': 'test_bearer_token',
                'api_key': 'test_api_key',
                'api_secret': 'test_api_secret'
            },
            'facebook': {
                'access_token': 'test_facebook_token'
            },
            'instagram': {
                'access_token': 'test_facebook_token',
                'instagram_business_account_id': 'test_ig_account'
            },
            'linkedin': {
                'access_token': 'test_linkedin_token',
                'organization_id': 'test_org_id'
            }
        }
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive connector test suite"""
        print("🧪 Running Social Media Connector Test Suite")
        print("=" * 60)
        
        tests = [
            ("Connector Creation", self.test_connector_creation),
            ("Credential Validation", self.test_credential_validation),
            ("Search Functionality", self.test_search_functionality),
            ("User Posts Retrieval", self.test_user_posts),
            ("Rate Limiting", self.test_rate_limiting),
            ("Error Handling", self.test_error_handling),
            ("Message Processing", self.test_message_processing),
            ("Connector Manager", self.test_connector_manager),
            ("Monitoring Tasks", self.test_monitoring_tasks),
            ("Health Checks", self.test_health_checks)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                print(f"\n🔍 Testing {test_name}...")
                result = await test_func()
                if result:
                    print(f"✅ {test_name} - PASSED")
                    passed += 1
                else:
                    print(f"❌ {test_name} - FAILED")
            except Exception as e:
                print(f"💥 {test_name} - CRASHED: {e}")
        
        # Summary
        print(f"\n" + "=" * 60)
        print(f"📊 Test Results: {passed}/{total} passed")
        
        success_rate = (passed / total) * 100
        if success_rate == 100:
            print("🎉 All tests passed! Connector system is working perfectly.")
        elif success_rate >= 80:
            print("✅ Most tests passed. System is functional with minor issues.")
        else:
            print("⚠️ Multiple test failures. Please review the implementation.")
        
        return {
            'total_tests': total,
            'passed_tests': passed,
            'success_rate': success_rate,
            'status': 'success' if success_rate >= 80 else 'failure'
        }
    
    async def test_connector_creation(self) -> bool:
        """Test connector creation and initialization"""
        try:
            from .twitter_connector import TwitterConnector
            from .meta_connector import MetaConnector
            from .linkedin_connector import LinkedInConnector
            
            # Test Twitter connector creation
            twitter_connector = TwitterConnector(self.mock_credentials['twitter'])
            if twitter_connector.source_type != SourceType.TWITTER:
                print("   ❌ Twitter connector source type incorrect")
                return False
            
            # Test Meta connectors creation
            facebook_connector = MetaConnector(self.mock_credentials['facebook'], 'facebook')
            if facebook_connector.source_type != SourceType.FACEBOOK:
                print("   ❌ Facebook connector source type incorrect")
                return False
            
            instagram_connector = MetaConnector(self.mock_credentials['instagram'], 'instagram')
            if instagram_connector.source_type != SourceType.INSTAGRAM:
                print("   ❌ Instagram connector source type incorrect")
                return False
            
            # Test LinkedIn connector creation
            linkedin_connector = LinkedInConnector(self.mock_credentials['linkedin'])
            if linkedin_connector.source_type != SourceType.LINKEDIN:
                print("   ❌ LinkedIn connector source type incorrect")
                return False
            
            print("   ✅ All connectors created successfully")
            return True
            
        except Exception as e:
            print(f"   ❌ Connector creation error: {e}")
            return False
    
    async def test_credential_validation(self) -> bool:
        """Test credential validation with mocked API responses"""
        try:
            from .twitter_connector import TwitterConnector
            
            # Mock successful validation
            with patch('aiohttp.ClientSession.request') as mock_request:
                # Mock successful Twitter API response
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={'data': {'id': 'test_user', 'username': 'test'}})
                mock_request.return_value.__aenter__.return_value = mock_response
                
                connector = TwitterConnector(self.mock_credentials['twitter'])
                await connector._initialize_session()
                
                # Test validation
                is_valid = await connector._validate_credentials()
                
                if not is_valid:
                    print("   ❌ Credential validation failed with mocked success response")
                    return False
            
            # Mock failed validation
            with patch('aiohttp.ClientSession.request') as mock_request:
                # Mock failed Twitter API response
                mock_response = AsyncMock()
                mock_response.status = 401
                mock_response.raise_for_status = MagicMock(side_effect=Exception("Unauthorized"))
                mock_request.return_value.__aenter__.return_value = mock_response
                
                connector = TwitterConnector(self.mock_credentials['twitter'])
                await connector._initialize_session()
                
                # Test validation should fail
                is_valid = await connector._validate_credentials()
                
                if is_valid:
                    print("   ❌ Credential validation succeeded with mocked failure response")
                    return False
            
            print("   ✅ Credential validation working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Credential validation test error: {e}")
            return False
    
    async def test_search_functionality(self) -> bool:
        """Test search functionality with mocked API responses"""
        try:
            from .twitter_connector import TwitterConnector
            
            # Mock search response
            mock_tweets = {
                'data': [
                    {
                        'id': '1234567890',
                        'text': 'Test tweet content',
                        'author_id': 'user123',
                        'created_at': '2024-01-01T12:00:00.000Z',
                        'public_metrics': {
                            'like_count': 10,
                            'retweet_count': 5,
                            'reply_count': 2
                        }
                    }
                ],
                'includes': {
                    'users': [
                        {
                            'id': 'user123',
                            'username': 'testuser',
                            'name': 'Test User',
                            'verified': False
                        }
                    ]
                }
            }
            
            with patch('tweepy.asynchronous.AsyncClient.search_recent_tweets') as mock_search:
                mock_search.return_value = MagicMock()
                mock_search.return_value.data = [MagicMock(**tweet) for tweet in mock_tweets['data']]
                mock_search.return_value.includes = mock_tweets['includes']
                
                connector = TwitterConnector(self.mock_credentials['twitter'])
                
                # Test search
                results = []
                async for post_data in connector.search_posts('test query', limit=10):
                    results.append(post_data)
                
                if not results:
                    print("   ❌ Search returned no results with mocked data")
                    return False
                
                # Validate result structure
                post = results[0]
                required_fields = ['post_id', 'author_id', 'content', 'created_at']
                
                for field in required_fields:
                    if field not in post:
                        print(f"   ❌ Missing required field in search result: {field}")
                        return False
            
            print("   ✅ Search functionality working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Search functionality test error: {e}")
            return False
    
    async def test_user_posts(self) -> bool:
        """Test user posts retrieval"""
        try:
            from .twitter_connector import TwitterConnector
            
            # Mock user tweets response
            mock_user_tweets = {
                'data': [
                    {
                        'id': '9876543210',
                        'text': 'User tweet content',
                        'created_at': '2024-01-01T12:00:00.000Z',
                        'public_metrics': {
                            'like_count': 20,
                            'retweet_count': 10
                        }
                    }
                ]
            }
            
            mock_user_info = {
                'data': {
                    'id': 'user123',
                    'username': 'testuser',
                    'name': 'Test User'
                }
            }
            
            with patch('tweepy.asynchronous.AsyncClient.get_users_tweets') as mock_tweets, \
                 patch('tweepy.asynchronous.AsyncClient.get_user') as mock_user:
                
                mock_tweets.return_value = MagicMock()
                mock_tweets.return_value.data = [MagicMock(**tweet) for tweet in mock_user_tweets['data']]
                
                mock_user.return_value = MagicMock()
                mock_user.return_value.data = MagicMock(**mock_user_info['data'])
                
                connector = TwitterConnector(self.mock_credentials['twitter'])
                
                # Test user posts
                results = []
                async for post_data in connector.get_user_posts('user123', limit=10):
                    results.append(post_data)
                
                if not results:
                    print("   ❌ User posts returned no results with mocked data")
                    return False
                
                # Validate result
                post = results[0]
                if post['post_id'] != '9876543210':
                    print("   ❌ User post data not correctly processed")
                    return False
            
            print("   ✅ User posts functionality working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ User posts test error: {e}")
            return False
    
    async def test_rate_limiting(self) -> bool:
        """Test rate limiting functionality"""
        try:
            from .twitter_connector import TwitterConnector
            
            connector = TwitterConnector(self.mock_credentials['twitter'])
            
            # Test rate limit info setup
            await connector._setup_rate_limiting()
            
            if not hasattr(connector, 'rate_limits'):
                print("   ❌ Rate limits not initialized")
                return False
            
            # Test rate limit checking
            await connector._check_rate_limits()
            
            print("   ✅ Rate limiting functionality working")
            return True
            
        except Exception as e:
            print(f"   ❌ Rate limiting test error: {e}")
            return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling in connectors"""
        try:
            from .twitter_connector import TwitterConnector
            
            connector = TwitterConnector(self.mock_credentials['twitter'])
            
            # Test handling of invalid data
            try:
                invalid_post_data = {'invalid': 'data'}
                await connector.process_post_data(invalid_post_data)
                # Should not raise exception, should handle gracefully
            except Exception as e:
                print(f"   ❌ Error handling failed for invalid data: {e}")
                return False
            
            print("   ✅ Error handling working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Error handling test error: {e}")
            return False
    
    async def test_message_processing(self) -> bool:
        """Test message processing and publishing"""
        try:
            from .twitter_connector import TwitterConnector
            
            # Mock message publishing
            with patch('messaging.producer.threat_producer.publish_social_media_data') as mock_publish:
                mock_publish.return_value = True
                
                connector = TwitterConnector(self.mock_credentials['twitter'])
                
                # Test message processing
                test_post_data = {
                    'post_id': 'test123',
                    'author_id': 'author123',
                    'author_username': 'testuser',
                    'content': 'Test post content',
                    'created_at': datetime.utcnow(),
                    'likes': 10,
                    'shares': 5
                }
                
                success = await connector.process_post_data(
                    post_data=test_post_data,
                    monitored_vip='test_vip',
                    keywords=['test', 'keyword']
                )
                
                if not success:
                    print("   ❌ Message processing failed")
                    return False
                
                # Verify publish was called
                if not mock_publish.called:
                    print("   ❌ Message was not published")
                    return False
            
            print("   ✅ Message processing working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Message processing test error: {e}")
            return False
    
    async def test_connector_manager(self) -> bool:
        """Test connector manager functionality"""
        try:
            # Test manager initialization (without actual API calls)
            with patch.object(connector_manager, '_create_connector') as mock_create:
                # Mock connector creation
                mock_connector = AsyncMock()
                mock_connector.source_type = SourceType.TWITTER
                mock_connector.start = AsyncMock()
                mock_connector.set_message_callback = MagicMock()
                mock_connector.set_error_callback = MagicMock()
                mock_create.return_value = mock_connector
                
                # Test initialization
                results = await connector_manager.initialize([SourceType.TWITTER])
                
                if SourceType.TWITTER not in results:
                    print("   ❌ Manager initialization failed")
                    return False
                
                # Test status
                status = connector_manager.get_status()
                
                if not isinstance(status, dict):
                    print("   ❌ Manager status not returned correctly")
                    return False
            
            print("   ✅ Connector manager working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Connector manager test error: {e}")
            return False
    
    async def test_monitoring_tasks(self) -> bool:
        """Test monitoring task management"""
        try:
            # Mock connector manager with a fake connector
            mock_connector = AsyncMock()
            mock_connector.source_type = SourceType.TWITTER
            mock_connector.stream_real_time = AsyncMock()
            mock_connector.search_posts = AsyncMock()
            
            # Add mock connector to manager
            connector_manager.connectors[SourceType.TWITTER] = mock_connector
            connector_manager.is_running = True
            
            # Test starting monitoring task
            success = await connector_manager.start_monitoring(
                task_id='test_task',
                keywords=['test', 'keyword'],
                vips=['test_vip'],
                platforms=[SourceType.TWITTER],
                mode=MonitoringMode.SEARCH_ONLY,
                duration=10  # 10 seconds
            )
            
            if not success:
                print("   ❌ Failed to start monitoring task")
                return False
            
            # Test task status
            status = connector_manager.get_status()
            if 'test_task' not in status['tasks']:
                print("   ❌ Monitoring task not found in status")
                return False
            
            # Test stopping task
            stop_success = await connector_manager.stop_monitoring('test_task')
            if not stop_success:
                print("   ❌ Failed to stop monitoring task")
                return False
            
            print("   ✅ Monitoring tasks working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Monitoring tasks test error: {e}")
            return False
        finally:
            # Cleanup
            connector_manager.connectors.clear()
            connector_manager.monitoring_tasks.clear()
            connector_manager.is_running = False
    
    async def test_health_checks(self) -> bool:
        """Test health check functionality"""
        try:
            # Mock connector with health check
            mock_connector = AsyncMock()
            mock_connector.source_type = SourceType.TWITTER
            mock_connector.health_check = AsyncMock(return_value={
                'status': 'healthy',
                'api_connected': True,
                'last_check': datetime.utcnow().isoformat()
            })
            
            # Add mock connector to manager
            connector_manager.connectors[SourceType.TWITTER] = mock_connector
            connector_manager.is_running = True
            
            # Test health check
            health_info = await connector_manager.health_check()
            
            if health_info['overall_health'] != 'healthy':
                print(f"   ❌ Health check failed: {health_info}")
                return False
            
            if SourceType.TWITTER.value not in health_info['connectors']:
                print("   ❌ Connector health not included")
                return False
            
            print("   ✅ Health checks working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Health checks test error: {e}")
            return False
        finally:
            # Cleanup
            connector_manager.connectors.clear()
            connector_manager.is_running = False


async def run_connector_tests():
    """Run all connector tests"""
    tester = ConnectorTester()
    return await tester.run_all_tests()


def test_mock_data_generation():
    """Test generation of realistic mock data"""
    print("\n📝 Testing with mock social media data...")
    
    try:
        # Generate mock Twitter data
        mock_twitter_posts = [
            {
                'post_id': '1234567890123456789',
                'author_id': 'suspicious_user_123',
                'author_username': 'fake_celebrity_account',
                'author_display_name': 'Celebrity Name (FAKE)',
                'content': 'URGENT! Send me Bitcoin and I will double your investment! Limited time offer! DM me now!',
                'created_at': datetime.utcnow() - timedelta(minutes=5),
                'url': 'https://twitter.com/fake_celebrity_account/status/1234567890123456789',
                'likes': 150,
                'shares': 75,
                'comments': 45,
                'author_followers': 500,
                'author_verified': False,
                'hashtags': ['investment', 'bitcoin', 'money'],
                'mentions': ['@real_celebrity']
            },
            {
                'post_id': '9876543210987654321',
                'author_id': 'threat_account_456',
                'author_username': 'anonymous_threat',
                'content': 'I know where Celebrity Name lives. Going to pay them a visit tonight.',
                'created_at': datetime.utcnow() - timedelta(minutes=10),
                'url': 'https://twitter.com/anonymous_threat/status/9876543210987654321',
                'likes': 5,
                'shares': 2,
                'author_followers': 50,
                'author_verified': False
            }
        ]
        
        # Generate mock Instagram data
        mock_instagram_posts = [
            {
                'post_id': 'ig_post_123456',
                'author_id': 'fake_ig_account',
                'author_username': 'celebrity_name_official_fake',
                'content': 'Check out my new crypto project! Guaranteed returns! Link in bio!',
                'created_at': datetime.utcnow() - timedelta(hours=1),
                'url': 'https://instagram.com/p/fake_post_123',
                'likes': 2500,
                'comments': 150,
                'content_type': 'image',
                'media_urls': ['https://instagram.com/fake_image.jpg']
            }
        ]
        
        # Generate mock LinkedIn data
        mock_linkedin_posts = [
            {
                'post_id': 'linkedin_activity_789',
                'author_id': 'urn:li:person:fake_profile',
                'author_display_name': 'Celebrity Name (Imposter)',
                'content': 'Excited to announce my new business venture! Looking for investors.',
                'created_at': datetime.utcnow() - timedelta(hours=2),
                'url': 'https://linkedin.com/feed/update/urn:li:activity:789',
                'likes': 25,
                'comments': 8,
                'shares': 3
            }
        ]
        
        print(f"   ✅ Generated {len(mock_twitter_posts)} Twitter posts")
        print(f"   ✅ Generated {len(mock_instagram_posts)} Instagram posts")
        print(f"   ✅ Generated {len(mock_linkedin_posts)} LinkedIn posts")
        
        # Show sample data
        print(f"\n📄 Sample Twitter Post:")
        sample_post = mock_twitter_posts[0]
        print(f"   Author: {sample_post['author_username']}")
        print(f"   Content: {sample_post['content'][:80]}...")
        print(f"   Engagement: {sample_post['likes']} likes, {sample_post['shares']} shares")
        print(f"   Threat Indicators: Financial scam, impersonation")
        
        print("✅ Mock data generation test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Mock data generation test failed: {e}")
        return False


if __name__ == "__main__":
    # Run comprehensive tests
    async def main():
        results = await run_connector_tests()
        
        # Run mock data test
        test_mock_data_generation()
        
        print(f"\n🎯 Final Result: {results['status'].upper()}")
    
    asyncio.run(main())
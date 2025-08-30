"""
Test suite for standardized message format
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any
from .schemas import MessageType, Priority, SourceType, ContentType
from .message_format import (
    message_format_manager,
    create_social_media_message,
    create_web_scraping_message,
    create_messaging_message,
    create_threat_analysis_message,
    create_incident_alert_message,
    create_evidence_request_message,
    create_system_event_message
)
from .serialization import serialize_message, deserialize_message
from .routing import message_router
from shared.logging_config import logger


class MessageFormatTester:
    """Test suite for message format functionality"""
    
    def __init__(self):
        self.test_results = []
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🧪 Running Message Format Test Suite")
        print("=" * 50)
        
        tests = [
            ("Schema Validation", self.test_schema_validation),
            ("Message Creation", self.test_message_creation),
            ("Serialization", self.test_serialization),
            ("Routing Logic", self.test_routing_logic),
            ("Message Enrichment", self.test_message_enrichment),
            ("Validation Rules", self.test_validation_rules),
            ("Format Conversion", self.test_format_conversion),
            ("Error Handling", self.test_error_handling)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                print(f"\n🔍 Testing {test_name}...")
                result = test_func()
                if result:
                    print(f"✅ {test_name} - PASSED")
                    passed += 1
                else:
                    print(f"❌ {test_name} - FAILED")
            except Exception as e:
                print(f"💥 {test_name} - CRASHED: {e}")
        
        # Summary
        print(f"\n" + "=" * 50)
        print(f"📊 Test Results: {passed}/{total} passed")
        
        success_rate = (passed / total) * 100
        if success_rate == 100:
            print("🎉 All tests passed! Message format system is working perfectly.")
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
    
    def test_schema_validation(self) -> bool:
        """Test message schema validation"""
        try:
            # Test valid social media message
            social_data = {
                'post_id': 'test_123',
                'author_id': 'user_456',
                'author_username': 'testuser',
                'content': 'This is a test post',
                'created_at': datetime.utcnow()
            }
            
            message = create_social_media_message(
                post_data=social_data,
                source=SourceType.TWITTER
            )
            
            # Validate message
            validation = message_format_manager.validate_message_format(message)
            
            if not validation['valid']:
                print(f"   ❌ Schema validation failed: {validation['errors']}")
                return False
            
            print("   ✅ Schema validation passed")
            return True
            
        except Exception as e:
            print(f"   ❌ Schema validation error: {e}")
            return False
    
    def test_message_creation(self) -> bool:
        """Test creation of different message types"""
        try:
            # Test social media message
            social_data = {
                'post_id': 'post_123',
                'author_id': 'author_456',
                'author_username': 'testuser',
                'content': 'Test social media content',
                'created_at': datetime.utcnow(),
                'likes': 10,
                'shares': 5
            }
            
            social_msg = create_social_media_message(
                post_data=social_data,
                source=SourceType.TWITTER,
                monitored_vip='test_vip',
                keywords=['test', 'keyword']
            )
            
            # Test web scraping message
            scraping_data = {
                'url': 'https://example.com/test',
                'title': 'Test Page',
                'content': 'Test web content',
                'scraped_at': datetime.utcnow()
            }
            
            scraping_msg = create_web_scraping_message(
                scraping_data=scraping_data,
                source=SourceType.PASTEBIN,
                search_query='test query'
            )
            
            # Test messaging message
            messaging_data = {
                'message_id': 'msg_123',
                'channel_id': 'channel_456',
                'author_id': 'user_789',
                'author_username': 'testuser',
                'content': 'Test messaging content',
                'created_at': datetime.utcnow()
            }
            
            messaging_msg = create_messaging_message(
                messaging_data=messaging_data,
                source=SourceType.TELEGRAM
            )
            
            # Test threat analysis message
            analysis_data = {
                'analysis_type': 'nlp_threat',
                'threat_detected': True,
                'confidence_score': 0.85,
                'threat_level': 'high',
                'findings': {'threat_indicators': ['suspicious_language']},
                'source_message_id': 'source_123'
            }
            
            analysis_msg = create_threat_analysis_message(
                analysis_data=analysis_data,
                source_message_id='source_123'
            )
            
            # Test incident alert message
            incident_data = {
                'title': 'Test Incident',
                'description': 'Test incident description',
                'severity': 'high',
                'category': 'impersonation',
                'affected_vip': 'test_vip',
                'confidence_score': 0.9
            }
            
            incident_msg = create_incident_alert_message(
                incident_data=incident_data
            )
            
            # Test evidence request message
            evidence_data = {
                'request_type': 'screenshot',
                'target_url': 'https://example.com/evidence',
                'target_description': 'Test evidence target'
            }
            
            evidence_msg = create_evidence_request_message(
                request_data=evidence_data
            )
            
            # Test system event message
            event_data = {
                'event_type': 'test_event',
                'component': 'message_format',
                'description': 'Test system event',
                'level': 'info'
            }
            
            system_msg = create_system_event_message(
                event_data=event_data
            )
            
            print("   ✅ All message types created successfully")
            return True
            
        except Exception as e:
            print(f"   ❌ Message creation error: {e}")
            return False
    
    def test_serialization(self) -> bool:
        """Test message serialization and deserialization"""
        try:
            # Create test message
            social_data = {
                'post_id': 'serialize_test',
                'author_id': 'author_test',
                'author_username': 'testuser',
                'content': 'Test serialization content',
                'created_at': datetime.utcnow()
            }
            
            original_msg = create_social_media_message(
                post_data=social_data,
                source=SourceType.TWITTER
            )
            
            # Serialize
            serialized = serialize_message(original_msg)
            
            # Deserialize
            deserialized_msg = deserialize_message(serialized)
            
            # Compare
            if (original_msg.message_id == deserialized_msg.message_id and
                original_msg.message_type == deserialized_msg.message_type and
                original_msg.source == deserialized_msg.source):
                print("   ✅ Serialization round-trip successful")
                return True
            else:
                print("   ❌ Serialization round-trip failed - data mismatch")
                return False
                
        except Exception as e:
            print(f"   ❌ Serialization error: {e}")
            return False
    
    def test_routing_logic(self) -> bool:
        """Test message routing logic"""
        try:
            # Test social media routing
            social_data = {
                'post_id': 'routing_test',
                'author_id': 'author_test',
                'author_username': 'testuser',
                'content': 'Test routing content',
                'created_at': datetime.utcnow()
            }
            
            social_msg = create_social_media_message(
                post_data=social_data,
                source=SourceType.TWITTER,
                priority=Priority.HIGH
            )
            
            routing_info = message_format_manager.get_routing_info(social_msg)
            
            # Verify routing
            expected_exchange = 'threat_data'
            expected_routing_key_pattern = 'social.twitter'
            
            if (routing_info['exchange'] == expected_exchange and
                routing_info['routing_key'] == expected_routing_key_pattern):
                print("   ✅ Message routing logic working correctly")
                return True
            else:
                print(f"   ❌ Routing mismatch - got {routing_info}")
                return False
                
        except Exception as e:
            print(f"   ❌ Routing logic error: {e}")
            return False
    
    def test_message_enrichment(self) -> bool:
        """Test message enrichment functionality"""
        try:
            # Create message with minimal data
            social_data = {
                'post_id': 'enrich_test',
                'author_id': 'author_test',
                'author_username': 'testuser',
                'content': 'Test enrichment content with @mention and #hashtag',
                'created_at': datetime.utcnow(),
                'likes': 100,
                'author_followers': 1000
            }
            
            message = create_social_media_message(
                post_data=social_data,
                source=SourceType.TWITTER
            )
            
            # Check enrichment
            metadata = message.metadata
            
            expected_enrichments = [
                'processed_at',
                'message_size',
                'word_count',
                'char_count',
                'has_mentions',
                'has_hashtags',
                'engagement_rate'
            ]
            
            missing_enrichments = [e for e in expected_enrichments if e not in metadata]
            
            if not missing_enrichments:
                print("   ✅ Message enrichment working correctly")
                return True
            else:
                print(f"   ❌ Missing enrichments: {missing_enrichments}")
                return False
                
        except Exception as e:
            print(f"   ❌ Message enrichment error: {e}")
            return False
    
    def test_validation_rules(self) -> bool:
        """Test message validation rules"""
        try:
            # Test valid message
            valid_data = {
                'post_id': 'valid_test',
                'author_id': 'author_test',
                'author_username': 'testuser',
                'content': 'Valid test content',
                'created_at': datetime.utcnow()
            }
            
            valid_msg = create_social_media_message(
                post_data=valid_data,
                source=SourceType.TWITTER
            )
            
            validation = message_format_manager.validate_message_format(valid_msg)
            
            if not validation['valid']:
                print(f"   ❌ Valid message failed validation: {validation['errors']}")
                return False
            
            # Test invalid message (missing required field)
            try:
                invalid_data = {
                    'author_id': 'author_test',
                    'content': 'Missing post_id',
                    'created_at': datetime.utcnow()
                }
                
                invalid_msg = create_social_media_message(
                    post_data=invalid_data,
                    source=SourceType.TWITTER
                )
                
                # This should fail during creation
                print("   ❌ Invalid message was created when it should have failed")
                return False
                
            except Exception:
                # Expected to fail
                pass
            
            print("   ✅ Validation rules working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Validation rules error: {e}")
            return False
    
    def test_format_conversion(self) -> bool:
        """Test format conversion utilities"""
        try:
            # Test message summary formatting
            social_data = {
                'post_id': 'format_test',
                'author_id': 'author_test',
                'author_username': 'testuser',
                'content': 'Test format conversion content',
                'created_at': datetime.utcnow()
            }
            
            message = create_social_media_message(
                post_data=social_data,
                source=SourceType.TWITTER
            )
            
            from .message_format import MessageFormatUtils
            
            # Test summary formatting
            summary = MessageFormatUtils.format_message_summary(message)
            
            if 'Type:' in summary and 'Source:' in summary:
                print("   ✅ Format conversion working correctly")
                return True
            else:
                print(f"   ❌ Summary format incorrect: {summary}")
                return False
                
        except Exception as e:
            print(f"   ❌ Format conversion error: {e}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling in message format system"""
        try:
            # Test invalid message type
            try:
                invalid_data = {
                    'message_type': 'invalid_type',
                    'source': 'twitter',
                    'data': {}
                }
                
                message_format_manager.process_raw_message(invalid_data)
                print("   ❌ Invalid message type was accepted")
                return False
                
            except ValueError:
                # Expected to fail
                pass
            
            # Test malformed serialization
            try:
                deserialize_message(b'invalid_data')
                print("   ❌ Invalid serialized data was accepted")
                return False
                
            except ValueError:
                # Expected to fail
                pass
            
            print("   ✅ Error handling working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Error handling test error: {e}")
            return False


def run_format_tests():
    """Run message format tests"""
    tester = MessageFormatTester()
    return tester.run_all_tests()


def test_message_examples():
    """Test with realistic message examples"""
    print("\n📝 Testing with realistic examples...")
    
    try:
        # Example 1: Twitter threat detection
        twitter_data = {
            'post_id': '1234567890',
            'author_id': 'suspicious_user',
            'author_username': 'fake_celebrity',
            'author_display_name': 'Celebrity Name',
            'content': 'Send me money and I will double it! Limited time offer!',
            'created_at': datetime.utcnow() - timedelta(minutes=5),
            'url': 'https://twitter.com/fake_celebrity/status/1234567890',
            'likes': 50,
            'shares': 25,
            'author_followers': 100,
            'author_verified': False,
            'hashtags': ['investment', 'money'],
            'mentions': ['@real_celebrity']
        }
        
        twitter_msg = create_social_media_message(
            post_data=twitter_data,
            source=SourceType.TWITTER,
            monitored_vip='real_celebrity',
            keywords=['money', 'investment', 'double'],
            priority=Priority.HIGH
        )
        
        print(f"   ✅ Twitter message: {twitter_msg.message_id}")
        
        # Example 2: Pastebin scraping result
        pastebin_data = {
            'url': 'https://pastebin.com/suspicious_paste',
            'title': 'Celebrity Personal Info',
            'content': 'Here is the personal information of Celebrity Name: Phone: 555-1234, Address: ...',
            'scraped_at': datetime.utcnow(),
            'author': 'anonymous',
            'word_count': 50,
            'language': 'en'
        }
        
        pastebin_msg = create_web_scraping_message(
            scraping_data=pastebin_data,
            source=SourceType.PASTEBIN,
            search_query='Celebrity Name personal info',
            monitored_vip='celebrity_name',
            priority=Priority.CRITICAL
        )
        
        print(f"   ✅ Pastebin message: {pastebin_msg.message_id}")
        
        # Example 3: Threat analysis result
        analysis_data = {
            'analysis_type': 'impersonation_detection',
            'threat_detected': True,
            'confidence_score': 0.92,
            'threat_level': 'critical',
            'findings': {
                'username_similarity': 0.95,
                'profile_image_match': False,
                'follower_ratio_suspicious': True,
                'content_similarity': 0.8
            },
            'indicators': ['username_similarity', 'suspicious_follower_ratio', 'impersonation_content'],
            'source_message_id': twitter_msg.message_id
        }
        
        analysis_msg = create_threat_analysis_message(
            analysis_data=analysis_data,
            source_message_id=twitter_msg.message_id,
            priority=Priority.CRITICAL
        )
        
        print(f"   ✅ Analysis message: {analysis_msg.message_id}")
        
        # Example 4: Incident alert
        incident_data = {
            'title': 'High-Confidence Celebrity Impersonation Detected',
            'description': 'Detected suspicious account impersonating celebrity with financial scam content',
            'severity': 'critical',
            'category': 'impersonation',
            'affected_vip': 'real_celebrity',
            'evidence_urls': [twitter_data['url']],
            'source_messages': [twitter_msg.message_id, analysis_msg.message_id],
            'threat_indicators': ['username_similarity', 'financial_scam', 'impersonation'],
            'confidence_score': 0.92
        }
        
        incident_msg = create_incident_alert_message(
            incident_data=incident_data,
            priority=Priority.CRITICAL
        )
        
        print(f"   ✅ Incident message: {incident_msg.message_id}")
        
        # Test routing for all messages
        for msg in [twitter_msg, pastebin_msg, analysis_msg, incident_msg]:
            routing = message_format_manager.get_routing_info(msg)
            print(f"   📍 {msg.message_type} -> {routing['exchange']}.{routing['routing_key']}")
        
        print("✅ Realistic examples test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Realistic examples test failed: {e}")
        return False


if __name__ == "__main__":
    # Run comprehensive tests
    results = run_format_tests()
    
    # Run realistic examples
    test_message_examples()
    
    print(f"\n🎯 Final Result: {results['status'].upper()}")
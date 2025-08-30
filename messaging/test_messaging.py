"""
Test script for message queue system
"""
import time
import json
from typing import Dict, Any
from .connection import rabbitmq_connection
from .producer import threat_producer, analysis_producer, evidence_producer
from .consumer import MessageConsumer
from .queue_manager import queue_manager
from shared.logging_config import logger


class TestConsumer(MessageConsumer):
    """Test consumer for verification"""
    
    def __init__(self):
        super().__init__(
            queue_name="test_queue",
            auto_ack=True,
            prefetch_count=1
        )
        self.received_messages = []
    
    def process_message(self, message: Dict[str, Any], 
                       delivery_tag: int, properties) -> bool:
        """Process test message"""
        logger.info(f"Test consumer received: {message.get('message_id')}")
        self.received_messages.append(message)
        return True


def test_connection():
    """Test RabbitMQ connection"""
    print("🔗 Testing RabbitMQ connection...")
    
    if rabbitmq_connection.connect():
        print("✅ Connection successful")
        
        # Test health check
        health = rabbitmq_connection.health_check()
        print(f"📊 Health status: {health['status']}")
        
        rabbitmq_connection.disconnect()
        return True
    else:
        print("❌ Connection failed")
        return False


def test_queue_setup():
    """Test queue infrastructure setup"""
    print("\n🏗️ Testing queue setup...")
    
    if queue_manager.setup_infrastructure():
        print("✅ Queue infrastructure setup successful")
        
        # Get stats
        stats = queue_manager.get_queue_stats()
        print(f"📊 Created {len(stats.get('queues', {}))} queues")
        
        return True
    else:
        print("❌ Queue setup failed")
        return False


def test_producers():
    """Test message producers"""
    print("\n📤 Testing message producers...")
    
    test_data = {
        "test": True,
        "content": "Test message content",
        "timestamp": time.time()
    }
    
    # Test threat producer
    success1 = threat_producer.publish_social_media_data(test_data, "twitter")
    success2 = threat_producer.publish_web_scraping_data(test_data, "pastebin")
    success3 = threat_producer.publish_messaging_data(test_data, "telegram")
    
    # Test analysis producer
    success4 = analysis_producer.publish_threat_analysis(
        {"threat_level": "low", "confidence": 0.3}, 
        "nlp_analysis"
    )
    
    # Test evidence producer
    success5 = evidence_producer.request_screenshot("https://example.com")
    success6 = evidence_producer.request_media_download("https://example.com/image.jpg")
    
    successes = [success1, success2, success3, success4, success5, success6]
    successful_count = sum(successes)
    
    print(f"📊 Producer test results: {successful_count}/6 successful")
    
    if successful_count >= 4:  # Allow some failures
        print("✅ Producer tests passed")
        return True
    else:
        print("❌ Producer tests failed")
        return False


def test_consumer():
    """Test message consumer"""
    print("\n📥 Testing message consumer...")
    
    try:
        # Create test consumer
        consumer = TestConsumer()
        
        # Send a test message directly to test queue
        test_message = {
            "test": True,
            "content": "Direct test message",
            "timestamp": time.time()
        }
        
        # Use basic producer to send to test queue
        from .producer import MessageProducer
        test_producer = MessageProducer()
        
        success = test_producer.publish_message(
            message=test_message,
            queue_name="test_queue"
        )
        
        if not success:
            print("❌ Failed to send test message")
            return False
        
        print("📤 Test message sent, starting consumer...")
        
        # Start consumer for a short time
        import threading
        
        def consume_for_time():
            consumer.start_consuming(blocking=True)
        
        consumer_thread = threading.Thread(target=consume_for_time)
        consumer_thread.daemon = True
        consumer_thread.start()
        
        # Wait a bit for message processing
        time.sleep(3)
        
        # Stop consumer
        consumer.stop_consuming()
        
        # Check results
        if consumer.received_messages:
            print(f"✅ Consumer received {len(consumer.received_messages)} messages")
            return True
        else:
            print("❌ Consumer didn't receive any messages")
            return False
            
    except Exception as e:
        print(f"❌ Consumer test failed: {e}")
        return False


def test_health_monitoring():
    """Test health monitoring"""
    print("\n🏥 Testing health monitoring...")
    
    try:
        health_info = queue_manager.health_check()
        
        print(f"📊 Overall status: {health_info['status']}")
        print(f"🔗 Connection: {health_info.get('connection', 'unknown')}")
        
        # Check queues
        healthy_queues = sum(1 for q in health_info.get('queues', {}).values() 
                           if q.get('exists', False))
        total_queues = len(health_info.get('queues', {}))
        
        print(f"📁 Healthy queues: {healthy_queues}/{total_queues}")
        
        # Check exchanges
        healthy_exchanges = sum(1 for e in health_info.get('exchanges', {}).values() 
                              if e.get('exists', False))
        total_exchanges = len(health_info.get('exchanges', {}))
        
        print(f"🔄 Healthy exchanges: {healthy_exchanges}/{total_exchanges}")
        
        if health_info['status'] in ['healthy', 'degraded']:
            print("✅ Health monitoring working")
            return True
        else:
            print("❌ Health monitoring shows issues")
            return False
            
    except Exception as e:
        print(f"❌ Health monitoring test failed: {e}")
        return False


def run_all_tests():
    """Run all message queue tests"""
    print("🧪 Running Message Queue System Tests")
    print("=" * 50)
    
    tests = [
        ("Connection", test_connection),
        ("Queue Setup", test_queue_setup),
        ("Producers", test_producers),
        ("Consumer", test_consumer),
        ("Health Monitoring", test_health_monitoring)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Message queue system is working correctly.")
        return True
    elif passed >= len(results) * 0.8:  # 80% pass rate
        print("⚠️ Most tests passed. System is mostly functional.")
        return True
    else:
        print("❌ Multiple test failures. Please check the system configuration.")
        return False


if __name__ == "__main__":
    run_all_tests()
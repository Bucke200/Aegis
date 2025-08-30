#!/usr/bin/env python3
"""
Simple test script for Aegis Twitter functionality
Tests Twitter connection without requiring RabbitMQ or database
"""
import asyncio
import sys
from shared.config import settings
from shared.logging_config import logger


async def test_twitter_connection():
    """Test Twitter API connection"""
    print("🧪 Testing Twitter API connection...")
    
    # Check if Bearer Token is configured
    if not settings.twitter_bearer_token:
        print("❌ Twitter Bearer Token not configured")
        print("💡 Please set TWITTER_BEARER_TOKEN in your .env file")
        return False
    
    try:
        # Import and test tweepy directly
        import tweepy
        
        # Create API client
        client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
        
        print("🔍 Testing Twitter search...")
        
        # Simple search test
        tweets = client.search_recent_tweets(
            query="hello world",
            max_results=10,
            tweet_fields=['author_id', 'created_at', 'public_metrics']
        )
        
        if tweets.data:
            print(f"✅ Twitter connection successful! Found {len(tweets.data)} tweets")
            
            # Show first tweet
            first_tweet = tweets.data[0]
            print(f"\n📝 Sample tweet:")
            print(f"   ID: {first_tweet.id}")
            print(f"   Content: {first_tweet.text[:100]}...")
            print(f"   Created: {first_tweet.created_at}")
            
            if first_tweet.public_metrics:
                metrics = first_tweet.public_metrics
                print(f"   Likes: {metrics.get('like_count', 0)}")
                print(f"   Retweets: {metrics.get('retweet_count', 0)}")
            
            return True
        else:
            print("⚠️ Twitter connection works but no results found")
            return True
            
    except Exception as e:
        print(f"❌ Twitter test failed: {e}")
        print("\n💡 Troubleshooting:")
        print("1. Make sure TWITTER_BEARER_TOKEN is set in .env file")
        print("2. Verify your Bearer Token is valid")
        print("3. Check your internet connection")
        return False


async def test_config():
    """Test configuration loading"""
    print("🔧 Testing configuration...")
    
    try:
        print(f"✅ Config loaded successfully")
        print(f"   Twitter Bearer Token: {'✅ Set' if settings.twitter_bearer_token else '❌ Not set'}")
        print(f"   Database URL: {settings.database_url}")
        print(f"   Log Level: {settings.log_level}")
        return True
        
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🚀 Aegis Simple Test Suite")
    print("=" * 40)
    
    tests = [
        ("Configuration", test_config),
        ("Twitter Connection", test_twitter_connection),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running {test_name} test...")
        try:
            results[test_name] = await test_func()
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 40)
    print("📊 Test Results Summary:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your Aegis setup is working correctly.")
        return 0
    else:
        print("⚠️ Some tests failed. Please check the configuration.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
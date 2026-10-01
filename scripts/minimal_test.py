#!/usr/bin/env python3
"""
Minimal Aegis test with SQLite database but no RabbitMQ
"""
import asyncio
from shared.config import settings
from shared.logging_config import logger
from storage.database import init_database


async def test_database():
    """Test SQLite database initialization"""
    print("🗄️ Testing SQLite database...")
    
    try:
        # Initialize database
        await init_database()
        print("✅ SQLite database initialized successfully!")
        print(f"   Database file: {settings.database_url}")
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


async def test_twitter():
    """Test Twitter connection"""
    print("🐦 Testing Twitter API...")
    
    try:
        import tweepy
        client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
        
        tweets = client.search_recent_tweets(
            query="hello world",
            max_results=10,
            tweet_fields=['author_id', 'created_at']
        )
        
        if tweets.data:
            print(f"✅ Twitter API working! Found {len(tweets.data)} tweets")
            return True
        else:
            print("⚠️ Twitter API working but no results")
            return True
            
    except Exception as e:
        print(f"❌ Twitter test failed: {e}")
        return False


async def main():
    """Run minimal tests"""
    print("🚀 Aegis Minimal Test (SQLite + Twitter)")
    print("=" * 50)
    
    tests = [
        ("SQLite Database", test_database),
        ("Twitter API", test_twitter),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}...")
        try:
            results[test_name] = await test_func()
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n{'='*50}")
    print("📊 Results:")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print(f"\n🎯 {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Core functionality working!")
        print("💡 Install RabbitMQ to enable full messaging features")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
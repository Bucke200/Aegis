#!/usr/bin/env python3
"""
Check Twitter API rate limits
"""
import tweepy
from shared.config import settings
from shared.logging_config import logger

def check_rate_limits():
    """Check current Twitter API rate limits"""
    try:
        client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
        
        print("🔍 Checking Twitter API Rate Limits")
        print("=" * 40)
        
        # Try to get rate limit status
        try:
            # Make a simple request to check if API is working
            response = client.get_me()
            if response.data:
                print("✅ Twitter API connection successful")
                print(f"   Authenticated as: {response.data.username}")
            else:
                print("✅ Twitter API connection successful (bearer token only)")
        except tweepy.Unauthorized:
            print("❌ Twitter API unauthorized")
            print("   Check your TWITTER_BEARER_TOKEN in .env file")
            return
        except Exception as e:
            print(f"❌ API Error: {e}")
            return
        
        # Try a small search to test search endpoint
        try:
            print("\n🧪 Testing search endpoint...")
            test_tweets = client.search_recent_tweets(
                query="hello -is:retweet",
                max_results=10
            )
            
            if test_tweets.data:
                print(f"✅ Search working - found {len(test_tweets.data)} tweets")
            else:
                print("✅ Search endpoint working (no results for test query)")
                
        except tweepy.TooManyRequests:
            print("⚠️ Rate limit exceeded on search endpoint")
            print("   You've hit the free tier limit (300 requests per 15 minutes)")
            print("   Wait 15 minutes before making more requests")
        except Exception as e:
            print(f"❌ Search test failed: {e}")
        
        print("\n📊 Rate Limit Info:")
        print("   Free Tier: 300 requests per 15 minutes")
        print("   Recommended: Wait 10+ seconds between searches")
        print("   For higher limits: Upgrade to Twitter API Pro")
        
    except Exception as e:
        print(f"❌ Failed to check rate limits: {e}")
        logger.error(f"Rate limit check error: {e}")

if __name__ == "__main__":
    check_rate_limits()
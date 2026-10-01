#!/usr/bin/env python3
"""
Twitter-only test without database or messaging dependencies
"""
import asyncio
import tweepy
from shared.config import settings
from shared.logging_config import logger


class SimpleTwitterMonitor:
    """Simple Twitter monitoring without infrastructure dependencies"""
    
    def __init__(self):
        self.client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
    
    def search_tweets(self, query: str, max_results: int = 10):
        """Search for tweets"""
        try:
            tweets = self.client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=['author_id', 'created_at', 'public_metrics', 'context_annotations']
            )
            
            if tweets.data:
                print(f"Found {len(tweets.data)} tweets for query: '{query}'")
                for i, tweet in enumerate(tweets.data, 1):
                    print(f"\n--- Tweet {i} ---")
                    print(f"ID: {tweet.id}")
                    print(f"Content: {tweet.text}")
                    print(f"Created: {tweet.created_at}")
                    
                    if tweet.public_metrics:
                        metrics = tweet.public_metrics
                        print(f"Likes: {metrics.get('like_count', 0)}")
                        print(f"Retweets: {metrics.get('retweet_count', 0)}")
                        print(f"Replies: {metrics.get('reply_count', 0)}")
            else:
                print(f"No tweets found for query: '{query}'")
                
        except Exception as e:
            print(f"Error searching tweets: {e}")
    
    def monitor_keywords(self, keywords: list, max_results: int = 10):
        """Monitor multiple keywords"""
        for keyword in keywords:
            print(f"\n{'='*50}")
            print(f"Monitoring keyword: {keyword}")
            print(f"{'='*50}")
            self.search_tweets(keyword, max_results)


def main():
    """Main function"""
    print("🐦 Aegis Twitter Monitor (Standalone)")
    print("=" * 50)
    
    # Initialize monitor
    monitor = SimpleTwitterMonitor()
    
    # Example keywords to monitor
    keywords = [
        "cybersecurity threat",
        "data breach",
        "malware alert"
    ]
    
    # Monitor keywords
    monitor.monitor_keywords(keywords, max_results=5)
    
    print(f"\n{'='*50}")
    print("✅ Twitter monitoring test completed!")


if __name__ == "__main__":
    main()
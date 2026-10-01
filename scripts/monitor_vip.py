#!/usr/bin/env python3
"""
On-demand VIP threat search with rate limit management
"""
import asyncio
import time
import argparse
from datetime import datetime, timedelta
import tweepy
from shared.config import settings
from shared.logging_config import logger


class VIPThreatSearcher:
    """On-demand VIP threat search with rate limiting"""
    
    def __init__(self):
        self.client = tweepy.Client(bearer_token=settings.twitter_bearer_token)
        self.last_request_time = 0
        self.request_count = 0
        self.window_start = time.time()
        
    def _check_rate_limit(self):
        """Check if we can make a request"""
        current_time = time.time()
        
        # Reset counter every 15 minutes
        if current_time - self.window_start > 900:  # 15 minutes
            self.request_count = 0
            self.window_start = current_time
        
        # Twitter free tier: 300 requests per 15 minutes
        # Be more conservative with only 50 requests per 15 minutes
        if self.request_count >= 50:
            wait_time = 900 - (current_time - self.window_start)
            logger.warning(f"Rate limit reached. Waiting {wait_time:.0f} seconds")
            return False
        
        # Ensure minimum 10 seconds between requests for free tier
        time_since_last = current_time - self.last_request_time
        if time_since_last < 10:
            sleep_time = 10 - time_since_last
            logger.info(f"Rate limiting: waiting {sleep_time:.1f} seconds")
            time.sleep(sleep_time)
        
        return True
    
    def search_vip_mentions(self, vip_name: str, keywords: list = None):
        """Search for VIP mentions with rate limiting"""
        if not self._check_rate_limit():
            logger.warning("Rate limit exceeded, skipping search")
            return []
        
        try:
            # Build search query
            if keywords:
                # Search for VIP name + specific keywords
                query = f'"{vip_name}" ({" OR ".join(keywords)})'
            else:
                # Just search for VIP name
                query = f'"{vip_name}"'
            
            # Add filters to reduce noise
            query += " -is:retweet lang:en"
            
            logger.info(f"Searching Twitter for: {query}")
            
            tweets = self.client.search_recent_tweets(
                query=query,
                max_results=10,  # Small batch to conserve rate limit
                tweet_fields=['author_id', 'created_at', 'public_metrics', 'context_annotations'],
                user_fields=['username', 'verified']
            )
            
            self.request_count += 1
            self.last_request_time = time.time()
            
            if tweets.data:
                logger.info(f"Found {len(tweets.data)} tweets for {vip_name}")
                return self._process_tweets(tweets.data, vip_name)
            else:
                logger.info(f"No tweets found for {vip_name}")
                return []
                
        except tweepy.TooManyRequests:
            logger.error(f"Rate limit exceeded for {vip_name}. Wait 15 minutes before next search.")
            print(f"⚠️ Rate limit hit. Twitter allows limited searches on free tier.")
            print(f"💡 Wait 15 minutes or upgrade to Twitter API Pro for higher limits.")
            return []
        except tweepy.Unauthorized:
            logger.error(f"Twitter API unauthorized. Check your bearer token.")
            print(f"❌ Twitter API access denied. Check your credentials in .env file.")
            return []
        except Exception as e:
            logger.error(f"Error searching for {vip_name}: {e}")
            print(f"❌ Search error: {e}")
            return []
    
    def _process_tweets(self, tweets, vip_name):
        """Process and analyze tweets"""
        results = []
        
        for tweet in tweets:
            # Basic threat indicators
            threat_score = self._calculate_threat_score(tweet.text)
            
            result = {
                'vip_name': vip_name,
                'tweet_id': tweet.id,
                'content': tweet.text,
                'author_id': tweet.author_id,
                'created_at': tweet.created_at,
                'threat_score': threat_score,
                'metrics': tweet.public_metrics,
                'timestamp': datetime.now()
            }
            
            results.append(result)
            
            # Log high-threat tweets
            if threat_score > 0.7:
                logger.warning(f"HIGH THREAT detected for {vip_name}: {tweet.text[:100]}...")
        
        return results
    
    def _calculate_threat_score(self, text: str) -> float:
        """Simple threat scoring based on keywords"""
        threat_keywords = [
            'kill', 'murder', 'assassinate', 'bomb', 'attack', 'threat',
            'violence', 'harm', 'hurt', 'destroy', 'eliminate', 'target'
        ]
        
        text_lower = text.lower()
        threat_count = sum(1 for keyword in threat_keywords if keyword in text_lower)
        
        # Simple scoring: more threat words = higher score
        return min(threat_count * 0.3, 1.0)
    
    def search_single_vip(self, vip_name: str, keywords: list = None, max_results: int = 20):
        """Search for a single VIP on-demand"""
        logger.info(f"Searching for threats against: {vip_name}")
        
        # Use default threat keywords if none provided
        if not keywords:
            keywords = ['threat', 'kill', 'attack', 'bomb', 'violence', 'harm', 'murder']
        
        results = self.search_vip_mentions(vip_name, keywords)
        
        if results:
            print(f"\n🔍 SEARCH RESULTS for '{vip_name}':")
            print("=" * 60)
            
            # Sort by threat score (highest first)
            results.sort(key=lambda x: x['threat_score'], reverse=True)
            
            for i, result in enumerate(results[:max_results], 1):
                threat_level = "🔴 HIGH" if result['threat_score'] > 0.7 else "🟡 MEDIUM" if result['threat_score'] > 0.3 else "🟢 LOW"
                
                print(f"\n{i}. {threat_level} THREAT (Score: {result['threat_score']:.2f})")
                print(f"   📅 {result['created_at']}")
                print(f"   👤 Author ID: {result['author_id']}")
                print(f"   📊 Likes: {result['metrics']['like_count']}, Retweets: {result['metrics']['retweet_count']}")
                print(f"   💬 \"{result['content'][:120]}{'...' if len(result['content']) > 120 else ''}\"")
                print(f"   🔗 https://twitter.com/i/web/status/{result['tweet_id']}")
        else:
            print(f"\n✅ No threats found for '{vip_name}'")
            print("This could mean:")
            print("  • No threatening content was posted recently")
            print("  • Content exists but doesn't match our threat keywords")
            print("  • Rate limits prevented full search")
        
        return results
    
    def interactive_search(self):
        """Interactive mode for searching VIPs"""
        print("\n🛡️ VIP Threat Search Tool")
        print("=" * 40)
        print("Enter VIP names to search for threats.")
        print("Type 'quit' or 'exit' to stop.\n")
        
        while True:
            try:
                vip_name = input("🔍 Enter VIP name to search: ").strip()
                
                if vip_name.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if not vip_name:
                    print("❌ Please enter a valid name")
                    continue
                
                # Ask for custom keywords (optional)
                custom_keywords = input("🔑 Custom keywords (optional, press Enter for default): ").strip()
                keywords = custom_keywords.split(',') if custom_keywords else None
                if keywords:
                    keywords = [k.strip() for k in keywords]
                
                # Perform search
                self.search_single_vip(vip_name, keywords)
                
                print("\n" + "─" * 60)
                
            except KeyboardInterrupt:
                print("\n👋 Search interrupted by user")
                break
            except Exception as e:
                logger.error(f"Search error: {e}")
                print(f"❌ Error during search: {e}")


def main():
    """Main search function"""
    parser = argparse.ArgumentParser(description='Search for VIP threats on-demand')
    parser.add_argument('--vip', '-v', type=str, help='VIP name to search for')
    parser.add_argument('--keywords', '-k', type=str, help='Comma-separated threat keywords')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive mode')
    parser.add_argument('--max-results', '-m', type=int, default=20, help='Maximum results to show')
    
    args = parser.parse_args()
    
    searcher = VIPThreatSearcher()
    
    if args.interactive:
        # Interactive mode
        searcher.interactive_search()
    elif args.vip:
        # Single search mode
        keywords = args.keywords.split(',') if args.keywords else None
        if keywords:
            keywords = [k.strip() for k in keywords]
        
        searcher.search_single_vip(args.vip, keywords, args.max_results)
    else:
        # No arguments - show help and start interactive mode
        print("🛡️ Aegis VIP Threat Search")
        print("=" * 30)
        print("\nUsage examples:")
        print("  python -m scripts.monitor_vip --vip \"Elon Musk\"")
        print("  python -m scripts.monitor_vip --vip \"Joe Biden\" --keywords \"threat,attack,harm\"")
        print("  python -m scripts.monitor_vip --interactive")
        print("\nStarting interactive mode...\n")
        searcher.interactive_search()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Search stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Application error: {e}")
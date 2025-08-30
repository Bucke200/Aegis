"""
CLI utilities for social media connector management
"""
import click
import asyncio
import json
import sys
import os
from typing import List
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from ingestion.connector_manager import connector_manager, MonitoringMode
from messaging.schemas import SourceType
from shared.logging_config import logger


@click.group()
def cli():
    """Social media connector management commands"""
    pass


@cli.command()
@click.option('--platforms', 
              help='Comma-separated list of platforms (twitter,facebook,instagram,linkedin)')
def init(platforms):
    """Initialize social media connectors"""
    click.echo("🚀 Initializing social media connectors...")
    
    async def _init():
        try:
            # Parse platforms
            platform_list = None
            if platforms:
                platform_names = [p.strip().lower() for p in platforms.split(',')]
                platform_list = []
                
                for name in platform_names:
                    if name == 'twitter':
                        platform_list.append(SourceType.TWITTER)
                    elif name == 'facebook':
                        platform_list.append(SourceType.FACEBOOK)
                    elif name == 'instagram':
                        platform_list.append(SourceType.INSTAGRAM)
                    elif name == 'linkedin':
                        platform_list.append(SourceType.LINKEDIN)
                    else:
                        click.echo(f"⚠️ Unknown platform: {name}")
            
            # Initialize connectors
            results = await connector_manager.initialize(platform_list)
            
            # Display results
            click.echo("\n📊 Initialization Results:")
            for platform, result in results.items():
                if result == "success":
                    click.echo(f"   ✅ {platform.value}: Connected")
                else:
                    click.echo(f"   ❌ {platform.value}: {result}")
            
            successful = sum(1 for r in results.values() if r == "success")
            total = len(results)
            
            if successful > 0:
                click.echo(f"\n🎉 {successful}/{total} connectors initialized successfully")
            else:
                click.echo(f"\n❌ No connectors initialized successfully")
                
        except Exception as e:
            click.echo(f"❌ Initialization failed: {e}")
    
    asyncio.run(_init())


@cli.command()
def status():
    """Show connector status"""
    click.echo("📊 Social Media Connector Status:")
    
    async def _status():
        try:
            status_info = connector_manager.get_status()
            
            click.echo(f"\n🔧 Manager Status: {'Running' if status_info['manager_running'] else 'Stopped'}")
            click.echo(f"📡 Active Connectors: {status_info['active_connectors']}")
            click.echo(f"📋 Active Tasks: {status_info['active_tasks']}")
            
            # Connector details
            if status_info['connectors']:
                click.echo(f"\n📱 Connector Details:")
                for platform, metrics in status_info['connectors'].items():
                    status_emoji = {
                        'running': '🟢',
                        'stopped': '🔴',
                        'error': '❌',
                        'rate_limited': '🟡'
                    }.get(metrics['status'], '❓')
                    
                    click.echo(f"   {status_emoji} {platform}:")
                    click.echo(f"      Status: {metrics['status']}")
                    click.echo(f"      Messages: {metrics['messages_processed']}")
                    click.echo(f"      API Calls: {metrics['api_calls_made']}")
                    click.echo(f"      Rate Limits: {metrics['rate_limit_hits']}")
                    click.echo(f"      Errors: {metrics['errors_encountered']}")
                    
                    if metrics['last_activity']:
                        click.echo(f"      Last Activity: {metrics['last_activity']}")
            
            # Task details
            if status_info['tasks']:
                click.echo(f"\n📋 Monitoring Tasks:")
                for task_id, task_info in status_info['tasks'].items():
                    active_emoji = '🟢' if task_info['active'] else '🔴'
                    click.echo(f"   {active_emoji} {task_id}:")
                    click.echo(f"      Keywords: {', '.join(task_info['keywords'])}")
                    click.echo(f"      VIPs: {', '.join(task_info['vips'])}")
                    click.echo(f"      Platforms: {', '.join(task_info['platforms'])}")
                    click.echo(f"      Mode: {task_info['mode']}")
                    click.echo(f"      Created: {task_info['created_at']}")
            
        except Exception as e:
            click.echo(f"❌ Failed to get status: {e}")
    
    asyncio.run(_status())


@cli.command()
def health():
    """Check connector health"""
    click.echo("🏥 Checking connector health...")
    
    async def _health():
        try:
            health_info = await connector_manager.health_check()
            
            # Overall health
            health_emoji = {
                'healthy': '✅',
                'degraded': '⚠️',
                'unhealthy': '❌',
                'stopped': '🔴'
            }.get(health_info['overall_health'], '❓')
            
            click.echo(f"\n{health_emoji} Overall Health: {health_info['overall_health']}")
            click.echo(f"🔧 Manager Status: {health_info['manager_status']}")
            
            # Connector health
            if health_info['connectors']:
                click.echo(f"\n📱 Connector Health:")
                for platform, health in health_info['connectors'].items():
                    status_emoji = {
                        'healthy': '✅',
                        'unhealthy': '❌',
                        'error': '💥'
                    }.get(health['status'], '❓')
                    
                    click.echo(f"   {status_emoji} {platform}: {health['status']}")
                    
                    if 'error' in health:
                        click.echo(f"      Error: {health['error']}")
                    
                    if 'api_connected' in health:
                        api_status = '✅' if health['api_connected'] else '❌'
                        click.echo(f"      API Connected: {api_status}")
            
        except Exception as e:
            click.echo(f"❌ Health check failed: {e}")
    
    asyncio.run(_health())


@cli.command()
@click.option('--task-id', required=True, help='Unique task identifier')
@click.option('--keywords', required=True, help='Comma-separated keywords to monitor')
@click.option('--vips', help='Comma-separated VIP names to monitor')
@click.option('--platforms', help='Comma-separated platforms (twitter,facebook,instagram,linkedin)')
@click.option('--mode', 
              type=click.Choice(['search_only', 'stream_only', 'hybrid', 'polling']),
              default='hybrid',
              help='Monitoring mode')
@click.option('--duration', type=int, help='Duration in seconds (omit for indefinite)')
def start_monitoring(task_id, keywords, vips, platforms, mode, duration):
    """Start monitoring task"""
    click.echo(f"🔍 Starting monitoring task: {task_id}")
    
    async def _start():
        try:
            # Parse keywords
            keyword_list = [k.strip() for k in keywords.split(',')]
            
            # Parse VIPs
            vip_list = []
            if vips:
                vip_list = [v.strip() for v in vips.split(',')]
            
            # Parse platforms
            platform_list = None
            if platforms:
                platform_names = [p.strip().lower() for p in platforms.split(',')]
                platform_list = []
                
                for name in platform_names:
                    if name == 'twitter':
                        platform_list.append(SourceType.TWITTER)
                    elif name == 'facebook':
                        platform_list.append(SourceType.FACEBOOK)
                    elif name == 'instagram':
                        platform_list.append(SourceType.INSTAGRAM)
                    elif name == 'linkedin':
                        platform_list.append(SourceType.LINKEDIN)
            
            # Convert mode
            monitoring_mode = MonitoringMode(mode)
            
            # Start monitoring
            success = await connector_manager.start_monitoring(
                task_id=task_id,
                keywords=keyword_list,
                vips=vip_list,
                platforms=platform_list,
                mode=monitoring_mode,
                duration=duration
            )
            
            if success:
                click.echo(f"✅ Monitoring task '{task_id}' started successfully")
                click.echo(f"   Keywords: {', '.join(keyword_list)}")
                if vip_list:
                    click.echo(f"   VIPs: {', '.join(vip_list)}")
                click.echo(f"   Mode: {mode}")
                if duration:
                    click.echo(f"   Duration: {duration} seconds")
                else:
                    click.echo(f"   Duration: Indefinite")
            else:
                click.echo(f"❌ Failed to start monitoring task '{task_id}'")
                
        except Exception as e:
            click.echo(f"❌ Failed to start monitoring: {e}")
    
    asyncio.run(_start())


@cli.command()
@click.option('--task-id', required=True, help='Task ID to stop')
def stop_monitoring(task_id):
    """Stop monitoring task"""
    click.echo(f"🛑 Stopping monitoring task: {task_id}")
    
    async def _stop():
        try:
            success = await connector_manager.stop_monitoring(task_id)
            
            if success:
                click.echo(f"✅ Monitoring task '{task_id}' stopped successfully")
            else:
                click.echo(f"❌ Failed to stop monitoring task '{task_id}' (task not found)")
                
        except Exception as e:
            click.echo(f"❌ Failed to stop monitoring: {e}")
    
    asyncio.run(_stop())


@cli.command()
def stop_all():
    """Stop all monitoring tasks"""
    click.echo("🛑 Stopping all monitoring tasks...")
    
    async def _stop_all():
        try:
            await connector_manager.stop_all_monitoring()
            click.echo("✅ All monitoring tasks stopped")
            
        except Exception as e:
            click.echo(f"❌ Failed to stop all monitoring: {e}")
    
    asyncio.run(_stop_all())


@cli.command()
@click.option('--platform', 
              type=click.Choice(['twitter', 'facebook', 'instagram', 'linkedin']),
              required=True,
              help='Platform to test')
@click.option('--query', default='test', help='Search query to test')
def test_search(platform, query):
    """Test search functionality for a platform"""
    click.echo(f"🔍 Testing {platform} search with query: '{query}'")
    
    async def _test():
        try:
            # Get platform connector
            platform_enum = {
                'twitter': SourceType.TWITTER,
                'facebook': SourceType.FACEBOOK,
                'instagram': SourceType.INSTAGRAM,
                'linkedin': SourceType.LINKEDIN
            }[platform]
            
            if platform_enum not in connector_manager.connectors:
                click.echo(f"❌ {platform} connector not available")
                return
            
            connector = connector_manager.connectors[platform_enum]
            
            # Perform search
            results = []
            async for post_data in connector.search_posts(query, limit=5):
                results.append(post_data)
            
            if results:
                click.echo(f"✅ Found {len(results)} results:")
                for i, post in enumerate(results, 1):
                    click.echo(f"\n--- Result {i} ---")
                    click.echo(f"ID: {post.get('post_id', 'unknown')}")
                    click.echo(f"Author: {post.get('author_username', 'unknown')}")
                    click.echo(f"Content: {post.get('content', '')[:100]}...")
                    click.echo(f"Created: {post.get('created_at', 'unknown')}")
                    click.echo(f"URL: {post.get('url', 'unknown')}")
            else:
                click.echo("📭 No results found")
                
        except Exception as e:
            click.echo(f"❌ Search test failed: {e}")
    
    asyncio.run(_test())


@cli.command()
@click.option('--platform',
              type=click.Choice(['twitter', 'facebook', 'instagram', 'linkedin']),
              required=True,
              help='Platform to test')
@click.option('--user-id', required=True, help='User ID or username to test')
def test_user_posts(platform, user_id):
    """Test user posts functionality"""
    click.echo(f"👤 Testing {platform} user posts for: {user_id}")
    
    async def _test():
        try:
            # Get platform connector
            platform_enum = {
                'twitter': SourceType.TWITTER,
                'facebook': SourceType.FACEBOOK,
                'instagram': SourceType.INSTAGRAM,
                'linkedin': SourceType.LINKEDIN
            }[platform]
            
            if platform_enum not in connector_manager.connectors:
                click.echo(f"❌ {platform} connector not available")
                return
            
            connector = connector_manager.connectors[platform_enum]
            
            # Get user posts
            results = []
            async for post_data in connector.get_user_posts(user_id, limit=5):
                results.append(post_data)
            
            if results:
                click.echo(f"✅ Found {len(results)} posts:")
                for i, post in enumerate(results, 1):
                    click.echo(f"\n--- Post {i} ---")
                    click.echo(f"ID: {post.get('post_id', 'unknown')}")
                    click.echo(f"Content: {post.get('content', '')[:100]}...")
                    click.echo(f"Created: {post.get('created_at', 'unknown')}")
                    click.echo(f"Likes: {post.get('likes', 0)}")
                    click.echo(f"Shares: {post.get('shares', 0)}")
            else:
                click.echo("📭 No posts found")
                
        except Exception as e:
            click.echo(f"❌ User posts test failed: {e}")
    
    asyncio.run(_test())


@cli.command()
def shutdown():
    """Shutdown connector manager"""
    click.echo("🔌 Shutting down connector manager...")
    
    async def _shutdown():
        try:
            await connector_manager.shutdown()
            click.echo("✅ Connector manager shutdown complete")
            
        except Exception as e:
            click.echo(f"❌ Shutdown failed: {e}")
    
    asyncio.run(_shutdown())


@cli.command()
@click.option('--output', help='Output file for configuration template')
def config_template(output):
    """Generate configuration template for social media APIs"""
    
    template = """# Aegis Social Media API Configuration Template
# Copy this to your .env file and fill in your API credentials

# Twitter/X API Configuration
# Get these from https://developer.twitter.com/
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

# Meta (Facebook/Instagram) API Configuration
# Get these from https://developers.facebook.com/
FACEBOOK_ACCESS_TOKEN=your_facebook_access_token
FACEBOOK_APP_ID=your_facebook_app_id
FACEBOOK_APP_SECRET=your_facebook_app_secret
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_instagram_business_account_id

# LinkedIn API Configuration
# Get these from https://developer.linkedin.com/
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token
LINKEDIN_ORGANIZATION_ID=your_linkedin_organization_id
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret

# Messaging Platform Bots
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DISCORD_BOT_TOKEN=your_discord_bot_token
"""
    
    if output:
        with open(output, 'w') as f:
            f.write(template)
        click.echo(f"✅ Configuration template saved to: {output}")
    else:
        click.echo("📝 Social Media API Configuration Template:")
        click.echo(template)


if __name__ == "__main__":
    cli()
"""
CLI utilities for web scraper management
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

from scraping.scraper_manager import scraper_manager, ScrapingMode
from messaging.schemas import SourceType
from shared.logging_config import logger


@click.group()
def cli():
    """Web scraper management commands"""
    pass


@cli.command()
@click.option('--sources', 
              help='Comma-separated list of sources (pastebin,github)')
def init(sources):
    """Initialize web scrapers"""
    click.echo("🚀 Initializing web scrapers...")
    
    async def _init():
        try:
            # Parse sources
            source_list = None
            if sources:
                source_names = [s.strip().lower() for s in sources.split(',')]
                source_list = []
                
                for name in source_names:
                    if name == 'pastebin':
                        source_list.append(SourceType.PASTEBIN)
                    elif name == 'github':
                        source_list.append(SourceType.GITHUB)
                    else:
                        click.echo(f"⚠️ Unknown source: {name}")
            
            # Initialize scrapers
            results = await scraper_manager.initialize(source_list)
            
            # Display results
            click.echo("\n📊 Initialization Results:")
            for source, result in results.items():
                if result == "success":
                    click.echo(f"   ✅ {source.value}: Connected")
                else:
                    click.echo(f"   ❌ {source.value}: {result}")
            
            successful = sum(1 for r in results.values() if r == "success")
            total = len(results)
            
            if successful > 0:
                click.echo(f"\n🎉 {successful}/{total} scrapers initialized successfully")
            else:
                click.echo(f"\n❌ No scrapers initialized successfully")
                
        except Exception as e:
            click.echo(f"❌ Initialization failed: {e}")
    
    asyncio.run(_init())


@cli.command()
def status():
    """Show scraper status"""
    click.echo("📊 Web Scraper Status:")
    
    async def _status():
        try:
            status_info = scraper_manager.get_status()
            
            click.echo(f"\n🔧 Manager Status: {'Running' if status_info['manager_running'] else 'Stopped'}")
            click.echo(f"🕷️ Active Scrapers: {status_info['active_scrapers']}")
            click.echo(f"📋 Active Tasks: {status_info['active_tasks']}")
            
            # Scraper details
            if status_info['scrapers']:
                click.echo(f"\n🕸️ Scraper Details:")
                for source, metrics in status_info['scrapers'].items():
                    status_emoji = {
                        'running': '🟢',
                        'stopped': '🔴',
                        'error': '❌',
                        'rate_limited': '🟡'
                    }.get(metrics['status'], '❓')
                    
                    click.echo(f"   {status_emoji} {source}:")
                    click.echo(f"      Status: {metrics['status']}")
                    click.echo(f"      Pages Scraped: {metrics['pages_scraped']}")
                    click.echo(f"      Requests Made: {metrics['requests_made']}")
                    click.echo(f"      Rate Limits: {metrics['rate_limit_hits']}")
                    click.echo(f"      Errors: {metrics['errors_encountered']}")
                    
                    if metrics['last_activity']:
                        click.echo(f"      Last Activity: {metrics['last_activity']}")
            
            # Task details
            if status_info['tasks']:
                click.echo(f"\n📋 Scraping Tasks:")
                for task_id, task_info in status_info['tasks'].items():
                    active_emoji = '🟢' if task_info['active'] else '🔴'
                    click.echo(f"   {active_emoji} {task_id}:")
                    click.echo(f"      Keywords: {', '.join(task_info['keywords'])}")
                    click.echo(f"      VIPs: {', '.join(task_info['vips'])}")
                    click.echo(f"      Sources: {', '.join(task_info['sources'])}")
                    click.echo(f"      Mode: {task_info['mode']}")
                    click.echo(f"      Interval: {task_info['interval']}s")
                    click.echo(f"      Created: {task_info['created_at']}")
            
        except Exception as e:
            click.echo(f"❌ Failed to get status: {e}")
    
    asyncio.run(_status())


@cli.command()
def health():
    """Check scraper health"""
    click.echo("🏥 Checking scraper health...")
    
    async def _health():
        try:
            health_info = await scraper_manager.health_check()
            
            # Overall health
            health_emoji = {
                'healthy': '✅',
                'degraded': '⚠️',
                'unhealthy': '❌',
                'stopped': '🔴'
            }.get(health_info['overall_health'], '❓')
            
            click.echo(f"\n{health_emoji} Overall Health: {health_info['overall_health']}")
            click.echo(f"🔧 Manager Status: {health_info['manager_status']}")
            
            # Scraper health
            if health_info['scrapers']:
                click.echo(f"\n🕸️ Scraper Health:")
                for source, health in health_info['scrapers'].items():
                    status_emoji = {
                        'healthy': '✅',
                        'unhealthy': '❌',
                        'error': '💥'
                    }.get(health['status'], '❓')
                    
                    click.echo(f"   {status_emoji} {source}: {health['status']}")
                    
                    if 'error' in health:
                        click.echo(f"      Error: {health['error']}")
                    
                    if 'site_accessible' in health:
                        site_status = '✅' if health['site_accessible'] else '❌'
                        click.echo(f"      Site Accessible: {site_status}")
            
        except Exception as e:
            click.echo(f"❌ Health check failed: {e}")
    
    asyncio.run(_health())


@cli.command()
@click.option('--task-id', required=True, help='Unique task identifier')
@click.option('--keywords', required=True, help='Comma-separated keywords to scrape')
@click.option('--vips', help='Comma-separated VIP names to monitor')
@click.option('--sources', help='Comma-separated sources (pastebin,github)')
@click.option('--mode', 
              type=click.Choice(['search_only', 'monitor_only', 'hybrid']),
              default='hybrid',
              help='Scraping mode')
@click.option('--duration', type=int, help='Duration in seconds (omit for indefinite)')
@click.option('--interval', type=int, default=600, help='Interval between scraping cycles in seconds')
def start_scraping(task_id, keywords, vips, sources, mode, duration, interval):
    """Start scraping task"""
    click.echo(f"🔍 Starting scraping task: {task_id}")
    
    async def _start():
        try:
            # Parse keywords
            keyword_list = [k.strip() for k in keywords.split(',')]
            
            # Parse VIPs
            vip_list = []
            if vips:
                vip_list = [v.strip() for v in vips.split(',')]
            
            # Parse sources
            source_list = None
            if sources:
                source_names = [s.strip().lower() for s in sources.split(',')]
                source_list = []
                
                for name in source_names:
                    if name == 'pastebin':
                        source_list.append(SourceType.PASTEBIN)
                    elif name == 'github':
                        source_list.append(SourceType.GITHUB)
            
            # Convert mode
            scraping_mode = ScrapingMode(mode)
            
            # Start scraping
            success = await scraper_manager.start_scraping(
                task_id=task_id,
                keywords=keyword_list,
                vips=vip_list,
                sources=source_list,
                mode=scraping_mode,
                duration=duration,
                interval=interval
            )
            
            if success:
                click.echo(f"✅ Scraping task '{task_id}' started successfully")
                click.echo(f"   Keywords: {', '.join(keyword_list)}")
                if vip_list:
                    click.echo(f"   VIPs: {', '.join(vip_list)}")
                click.echo(f"   Mode: {mode}")
                click.echo(f"   Interval: {interval} seconds")
                if duration:
                    click.echo(f"   Duration: {duration} seconds")
                else:
                    click.echo(f"   Duration: Indefinite")
            else:
                click.echo(f"❌ Failed to start scraping task '{task_id}'")
                
        except Exception as e:
            click.echo(f"❌ Failed to start scraping: {e}")
    
    asyncio.run(_start())


@cli.command()
@click.option('--task-id', required=True, help='Task ID to stop')
def stop_scraping(task_id):
    """Stop scraping task"""
    click.echo(f"🛑 Stopping scraping task: {task_id}")
    
    async def _stop():
        try:
            success = await scraper_manager.stop_scraping(task_id)
            
            if success:
                click.echo(f"✅ Scraping task '{task_id}' stopped successfully")
            else:
                click.echo(f"❌ Failed to stop scraping task '{task_id}' (task not found)")
                
        except Exception as e:
            click.echo(f"❌ Failed to stop scraping: {e}")
    
    asyncio.run(_stop())


@cli.command()
def stop_all():
    """Stop all scraping tasks"""
    click.echo("🛑 Stopping all scraping tasks...")
    
    async def _stop_all():
        try:
            await scraper_manager.stop_all_scraping()
            click.echo("✅ All scraping tasks stopped")
            
        except Exception as e:
            click.echo(f"❌ Failed to stop all scraping: {e}")
    
    asyncio.run(_stop_all())


@cli.command()
@click.option('--source', 
              type=click.Choice(['pastebin', 'github']),
              required=True,
              help='Source to test')
@click.option('--query', default='test', help='Search query to test')
def test_search(source, query):
    """Test search functionality for a source"""
    click.echo(f"🔍 Testing {source} search with query: '{query}'")
    
    async def _test():
        try:
            # Get source scraper
            source_enum = {
                'pastebin': SourceType.PASTEBIN,
                'github': SourceType.GITHUB
            }[source]
            
            if source_enum not in scraper_manager.scrapers:
                click.echo(f"❌ {source} scraper not available")
                return
            
            scraper = scraper_manager.scrapers[source_enum]
            
            # Perform search
            results = []
            async for content_data in scraper.search_content(query, limit=5):
                results.append(content_data)
            
            if results:
                click.echo(f"✅ Found {len(results)} results:")
                for i, content in enumerate(results, 1):
                    click.echo(f"\n--- Result {i} ---")
                    click.echo(f"Title: {content.get('title', 'unknown')}")
                    click.echo(f"URL: {content.get('url', 'unknown')}")
                    click.echo(f"Content: {content.get('content', '')[:100]}...")
                    click.echo(f"Word Count: {content.get('word_count', 0)}")
                    
                    # Show threat analysis if available
                    if 'threat_analysis' in content:
                        threat = content['threat_analysis']
                        if threat.get('threat_score', 0) > 0:
                            click.echo(f"⚠️ Threat Score: {threat['threat_score']:.2f}")
                    
                    # Show security analysis if available
                    if 'security_analysis' in content:
                        security = content['security_analysis']
                        if security.get('security_score', 0) > 0:
                            click.echo(f"🔒 Security Score: {security['security_score']:.2f}")
            else:
                click.echo("📭 No results found")
                
        except Exception as e:
            click.echo(f"❌ Search test failed: {e}")
    
    asyncio.run(_test())


@cli.command()
@click.option('--url', required=True, help='URL to scrape')
@click.option('--source', 
              type=click.Choice(['pastebin', 'github']),
              help='Source type (auto-detected if not specified)')
def scrape_url(url, source):
    """Scrape content from specific URL"""
    click.echo(f"🕷️ Scraping URL: {url}")
    
    async def _scrape():
        try:
            # Convert source if specified
            source_enum = None
            if source:
                source_enum = {
                    'pastebin': SourceType.PASTEBIN,
                    'github': SourceType.GITHUB
                }[source]
            
            # Scrape URL
            content_data = await scraper_manager.scrape_url_direct(url, source_enum)
            
            if content_data:
                click.echo("✅ Content scraped successfully:")
                click.echo(f"   Title: {content_data.get('title', 'unknown')}")
                click.echo(f"   Word Count: {content_data.get('word_count', 0)}")
                click.echo(f"   Language: {content_data.get('language', 'unknown')}")
                
                # Show content preview
                content = content_data.get('content', '')
                if len(content) > 200:
                    content = content[:200] + "..."
                click.echo(f"   Content: {content}")
                
                # Show analysis results
                if 'threat_analysis' in content_data:
                    threat = content_data['threat_analysis']
                    if threat.get('threat_score', 0) > 0:
                        click.echo(f"   ⚠️ Threat Score: {threat['threat_score']:.2f}")
                        if threat.get('detected_patterns'):
                            click.echo(f"   Detected Patterns: {len(threat['detected_patterns'])}")
                
                if 'security_analysis' in content_data:
                    security = content_data['security_analysis']
                    if security.get('security_score', 0) > 0:
                        click.echo(f"   🔒 Security Score: {security['security_score']:.2f}")
                        if security.get('detected_issues'):
                            click.echo(f"   Security Issues: {len(security['detected_issues'])}")
            else:
                click.echo("❌ Failed to scrape content")
                
        except Exception as e:
            click.echo(f"❌ URL scraping failed: {e}")
    
    asyncio.run(_scrape())


@cli.command()
def shutdown():
    """Shutdown scraper manager"""
    click.echo("🔌 Shutting down scraper manager...")
    
    async def _shutdown():
        try:
            await scraper_manager.shutdown()
            click.echo("✅ Scraper manager shutdown complete")
            
        except Exception as e:
            click.echo(f"❌ Shutdown failed: {e}")
    
    asyncio.run(_shutdown())


@cli.command()
@click.option('--output', help='Output file for configuration template')
def config_template(output):
    """Generate configuration template for web scrapers"""
    
    template = """# Aegis Web Scraper Configuration Template
# Copy this to your .env file and fill in your credentials

# GitHub Configuration (optional - improves rate limits and access)
# Get token from https://github.com/settings/tokens
GITHUB_TOKEN=your_github_personal_access_token

# Scraping Configuration
SCRAPING_USER_AGENT=Aegis-ThreatMonitor/1.0 (Security Research)
SCRAPING_REQUEST_DELAY=2.0
SCRAPING_MAX_RETRIES=3

# Rate Limiting (requests per time period)
PASTEBIN_REQUESTS_PER_MINUTE=20
PASTEBIN_REQUESTS_PER_HOUR=500
GITHUB_REQUESTS_PER_MINUTE=30
GITHUB_REQUESTS_PER_HOUR=1000
"""
    
    if output:
        with open(output, 'w') as f:
            f.write(template)
        click.echo(f"✅ Configuration template saved to: {output}")
    else:
        click.echo("📝 Web Scraper Configuration Template:")
        click.echo(template)


if __name__ == "__main__":
    cli()
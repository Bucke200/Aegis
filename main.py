"""
Aegis VIP Threat Monitoring Platform - Main Application
Simple Twitter threat detection system
"""
import asyncio
import signal
import sys
from typing import Dict, Any
from datetime import datetime
import click
from shared.config import settings
from shared.logging_config import logger
from messaging.connection import rabbitmq_connection
from messaging.queue_manager import queue_manager
from ingestion.connector_manager import connector_manager, MonitoringMode
from messaging.schemas import SourceType
from storage.database import init_database


class AegisApp:
    """Main Aegis application"""
    
    def __init__(self):
        self.is_running = False
        self.monitoring_task_id = None
    
    async def initialize(self):
        """Initialize all system components"""
        logger.info("🚀 Initializing Aegis VIP Threat Monitoring Platform...")
        
        insecure = settings.check_insecure_defaults()
        if insecure:
            logger.warning(f"⚠️ Using insecure default values for: {', '.join(insecure)}")
        
        try:
            # Initialize database
            logger.info("📊 Setting up database...")
            if not await init_database():
                raise Exception("Failed to initialize database")
            
            # Setup message queue infrastructure
            logger.info("📨 Setting up message queue...")
            if not queue_manager.setup_infrastructure():
                raise Exception("Failed to setup message queue")
            
            # Initialize Twitter connector
            logger.info("🐦 Initializing Twitter connector...")
            if not settings.twitter_bearer_token:
                logger.warning("⚠️ Twitter Bearer Token not configured. Please set TWITTER_BEARER_TOKEN in .env")
                return False
            
            results = await connector_manager.initialize([SourceType.TWITTER])
            
            if results.get(SourceType.TWITTER) != "success":
                logger.error(f"❌ Twitter connector initialization failed: {results.get(SourceType.TWITTER)}")
                return False
            
            logger.info("✅ Aegis platform initialized successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
    
    async def start_monitoring(self, vip_name: str, keywords: list = None):
        """Start monitoring for a VIP"""
        if not vip_name:
            logger.error("VIP name is required")
            return False
        
        # Default keywords if none provided
        if not keywords:
            keywords = [vip_name, f"{vip_name} scam", f"{vip_name} hack", f"{vip_name} leak"]
        
        logger.info(f"🔍 Starting monitoring for VIP: {vip_name}")
        logger.info(f"📝 Keywords: {', '.join(keywords)}")
        
        try:
            self.monitoring_task_id = f"vip_monitoring_{vip_name.lower().replace(' ', '_')}"
            
            success = await connector_manager.start_monitoring(
                task_id=self.monitoring_task_id,
                keywords=keywords,
                vips=[vip_name],
                platforms=[SourceType.TWITTER],
                mode=MonitoringMode.HYBRID,
                duration=None  # Run indefinitely
            )
            
            if success:
                logger.info(f"✅ Monitoring started for {vip_name}")
                self.is_running = True
                return True
            else:
                logger.error(f"❌ Failed to start monitoring for {vip_name}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting monitoring: {e}")
            return False
    
    async def stop_monitoring(self):
        """Stop current monitoring"""
        if self.monitoring_task_id:
            logger.info("🛑 Stopping monitoring...")
            await connector_manager.stop_monitoring(self.monitoring_task_id)
            self.monitoring_task_id = None
            self.is_running = False
            logger.info("✅ Monitoring stopped")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get system status"""
        try:
            # Get connector status
            connector_status = connector_manager.get_status()
            
            # Get queue health
            queue_health = queue_manager.health_check()
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'system_running': self.is_running,
                'monitoring_task': self.monitoring_task_id,
                'connectors': connector_status,
                'queue_health': queue_health
            }
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {'error': str(e)}
    
    async def shutdown(self):
        """Shutdown the application"""
        logger.info("🔌 Shutting down Aegis platform...")
        
        try:
            # Stop monitoring
            if self.is_running:
                await self.stop_monitoring()
            
            # Shutdown connector manager
            await connector_manager.shutdown()
            
            # Close message queue connection
            rabbitmq_connection.disconnect()
            
            logger.info("✅ Aegis platform shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Global app instance
app = AegisApp()


@click.group()
def cli():
    """Aegis VIP Threat Monitoring Platform"""
    pass


@cli.command()
def setup():
    """Setup the Aegis platform"""
    click.echo("🚀 Setting up Aegis VIP Threat Monitoring Platform...")
    
    async def _setup():
        success = await app.initialize()
        if success:
            click.echo("✅ Setup completed successfully!")
            click.echo("\n📝 Next steps:")
            click.echo("1. Configure your Twitter API credentials in .env file")
            click.echo("2. Run 'python main.py monitor --vip \"Celebrity Name\"' to start monitoring")
        else:
            click.echo("❌ Setup failed. Please check the logs.")
    
    asyncio.run(_setup())


@cli.command()
@click.option('--vip', required=True, help='VIP name to monitor (e.g., "Elon Musk")')
@click.option('--keywords', help='Additional keywords (comma-separated)')
def monitor(vip, keywords):
    """Start monitoring for a VIP"""
    click.echo(f"🔍 Starting monitoring for: {vip}")
    
    # Parse keywords
    keyword_list = []
    if keywords:
        keyword_list = [k.strip() for k in keywords.split(',')]
    
    async def _monitor():
        # Initialize if needed
        if not await app.initialize():
            click.echo("❌ Failed to initialize platform")
            return
        
        # Start monitoring
        success = await app.start_monitoring(vip, keyword_list)
        
        if not success:
            click.echo("❌ Failed to start monitoring")
            return
        
        click.echo(f"✅ Monitoring started for {vip}")
        click.echo("📊 Press Ctrl+C to stop monitoring and view results")
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            click.echo("\n🛑 Stopping monitoring...")
            asyncio.create_task(app.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Keep running until interrupted
            while app.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await app.shutdown()
    
    asyncio.run(_monitor())


@cli.command()
def status():
    """Show system status"""
    click.echo("📊 Aegis Platform Status:")
    
    async def _status():
        try:
            status = await app.get_status()
            
            if 'error' in status:
                click.echo(f"❌ Error: {status['error']}")
                return
            
            # System status
            system_status = "🟢 Running" if status['system_running'] else "🔴 Stopped"
            click.echo(f"\n🔧 System: {system_status}")
            
            if status['monitoring_task']:
                click.echo(f"📋 Active Task: {status['monitoring_task']}")
            
            # Connector status
            connectors = status.get('connectors', {})
            click.echo(f"\n🐦 Twitter Connector:")
            
            if connectors.get('connectors'):
                twitter_metrics = connectors['connectors'].get('twitter', {})
                if twitter_metrics:
                    click.echo(f"   Status: {twitter_metrics.get('status', 'unknown')}")
                    click.echo(f"   Messages Processed: {twitter_metrics.get('messages_processed', 0)}")
                    click.echo(f"   API Calls: {twitter_metrics.get('api_calls_made', 0)}")
                    click.echo(f"   Errors: {twitter_metrics.get('errors_encountered', 0)}")
                else:
                    click.echo("   Status: Not initialized")
            
            # Queue status
            queue_health = status.get('queue_health', {})
            queue_status = "🟢 Healthy" if queue_health.get('status') == 'healthy' else "🔴 Unhealthy"
            click.echo(f"\n📨 Message Queue: {queue_status}")
            
        except Exception as e:
            click.echo(f"❌ Failed to get status: {e}")
    
    asyncio.run(_status())


@cli.command()
def test():
    """Test Twitter connection"""
    click.echo("🧪 Testing Twitter connection...")
    
    async def _test():
        try:
            # Initialize platform
            if not await app.initialize():
                click.echo("❌ Failed to initialize platform")
                return
            
            # Test Twitter search
            from ingestion.twitter_connector import create_twitter_connector
            
            twitter = create_twitter_connector()
            await twitter.start()
            
            click.echo("🔍 Testing Twitter search...")
            
            # Search for a simple test query
            results = []
            async for tweet in twitter.search_posts("hello world", limit=5):
                results.append(tweet)
            
            if results:
                click.echo(f"✅ Twitter connection successful! Found {len(results)} tweets")
                
                # Show first result
                if results:
                    first_tweet = results[0]
                    click.echo(f"\n📝 Sample tweet:")
                    click.echo(f"   Author: @{first_tweet.get('author_username', 'unknown')}")
                    click.echo(f"   Content: {first_tweet.get('content', '')[:100]}...")
                    click.echo(f"   Likes: {first_tweet.get('likes', 0)}")
            else:
                click.echo("⚠️ Twitter connection works but no results found")
            
            await twitter.stop()
            
        except Exception as e:
            click.echo(f"❌ Twitter test failed: {e}")
            click.echo("\n💡 Make sure you have set TWITTER_BEARER_TOKEN in your .env file")
    
    asyncio.run(_test())


@cli.command()
def config():
    """Show configuration template"""
    click.echo("📝 Aegis Configuration Template")
    click.echo("=" * 40)
    
    template = """
# Create a .env file in the project root with these settings:

# Twitter API Configuration (Required)
# Get your Bearer Token from https://developer.twitter.com/
TWITTER_BEARER_TOKEN=your_twitter_bearer_token_here

# Optional: Full Twitter API credentials for enhanced features
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret

# Database (uses default PostgreSQL from Docker)
DATABASE_URL=postgresql://aegis:aegis123@localhost:5432/aegis

# Message Queue (uses default RabbitMQ from Docker)
RABBITMQ_URL=amqp://aegis:aegis123@localhost:5672/

# Logging
LOG_LEVEL=INFO
"""
    
    click.echo(template)
    
    # Check current configuration
    click.echo("\n🔍 Current Configuration Status:")
    
    if settings.twitter_bearer_token:
        click.echo("✅ Twitter Bearer Token: Configured")
    else:
        click.echo("❌ Twitter Bearer Token: Not configured")
    
    click.echo(f"📊 Database URL: {settings.database_url}")
    click.echo(f"📨 RabbitMQ URL: {settings.rabbitmq_url}")


if __name__ == "__main__":
    cli()
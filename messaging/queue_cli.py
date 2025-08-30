"""
CLI utilities for message queue management
"""
import click
import json
import sys
import os
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from messaging.connection import rabbitmq_connection
from messaging.queue_manager import queue_manager
from messaging.producer import threat_producer, analysis_producer, evidence_producer
from shared.logging_config import logger


@click.group()
def cli():
    """Message queue management commands"""
    pass


@cli.command()
def setup():
    """Setup message queue infrastructure"""
    click.echo("🚀 Setting up message queue infrastructure...")
    
    try:
        # Test connection first
        if not rabbitmq_connection.connect():
            click.echo("❌ Failed to connect to RabbitMQ")
            return
        
        # Setup infrastructure
        if queue_manager.setup_infrastructure():
            click.echo("✅ Message queue infrastructure setup completed")
            
            # Show status
            stats = queue_manager.get_queue_stats()
            click.echo(f"\n📊 Created {len(stats.get('queues', {}))} queues")
            for queue_name, queue_stats in stats.get('queues', {}).items():
                click.echo(f"   📁 {queue_name}: {queue_stats.get('messages', 0)} messages")
        else:
            click.echo("❌ Failed to setup message queue infrastructure")
            
    except Exception as e:
        click.echo(f"❌ Setup failed: {e}")


@cli.command()
def health():
    """Check message queue system health"""
    click.echo("🔍 Checking message queue health...")
    
    try:
        health_info = queue_manager.health_check()
        
        # Overall status
        status_emoji = {
            'healthy': '✅',
            'degraded': '⚠️',
            'unhealthy': '❌'
        }
        
        click.echo(f"{status_emoji.get(health_info['status'], '❓')} Status: {health_info['status']}")
        click.echo(f"🔗 Connection: {health_info.get('connection', 'unknown')}")
        
        # Queue status
        click.echo(f"\n📁 Queues:")
        for queue_name, queue_info in health_info.get('queues', {}).items():
            if queue_info.get('exists', False):
                click.echo(f"   ✅ {queue_name}: {queue_info.get('messages', 0)} messages, {queue_info.get('consumers', 0)} consumers")
            else:
                click.echo(f"   ❌ {queue_name}: {queue_info.get('error', 'Not accessible')}")
        
        # Exchange status
        click.echo(f"\n🔄 Exchanges:")
        for exchange_name, exchange_info in health_info.get('exchanges', {}).items():
            if exchange_info.get('exists', False):
                click.echo(f"   ✅ {exchange_name} ({exchange_info.get('type', 'unknown')})")
            else:
                click.echo(f"   ❌ {exchange_name}: {exchange_info.get('error', 'Not accessible')}")
        
        # Issues
        if health_info.get('issues'):
            click.echo(f"\n⚠️ Issues:")
            for issue in health_info['issues']:
                click.echo(f"   • {issue}")
        
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")


@cli.command()
def stats():
    """Show queue statistics"""
    click.echo("📊 Message Queue Statistics:")
    
    try:
        stats = queue_manager.get_queue_stats()
        
        if 'error' in stats:
            click.echo(f"❌ Failed to get statistics: {stats['error']}")
            return
        
        click.echo(f"\n📈 Overview:")
        click.echo(f"   Total messages: {stats.get('total_messages', 0)}")
        click.echo(f"   Total consumers: {stats.get('total_consumers', 0)}")
        
        click.echo(f"\n📁 Queue Details:")
        for queue_name, queue_stats in stats.get('queues', {}).items():
            if 'error' in queue_stats:
                click.echo(f"   ❌ {queue_name}: {queue_stats['error']}")
            else:
                messages = queue_stats.get('messages', 0)
                consumers = queue_stats.get('consumers', 0)
                status = "🟢" if consumers > 0 else "🔴" if messages > 0 else "⚪"
                click.echo(f"   {status} {queue_name}: {messages} messages, {consumers} consumers")
        
    except Exception as e:
        click.echo(f"❌ Failed to get statistics: {e}")


@cli.command()
@click.option('--queue', required=True, help='Queue name to purge')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
def purge(queue, confirm):
    """Purge all messages from a queue"""
    if not confirm:
        if not click.confirm(f"Are you sure you want to purge all messages from '{queue}'?"):
            click.echo("❌ Purge cancelled")
            return
    
    click.echo(f"🧹 Purging queue: {queue}")
    
    try:
        if queue_manager.purge_queue(queue):
            click.echo(f"✅ Queue '{queue}' purged successfully")
        else:
            click.echo(f"❌ Failed to purge queue '{queue}'")
    except Exception as e:
        click.echo(f"❌ Purge failed: {e}")


@cli.command()
@click.option('--queue', required=True, help='Queue name to sample')
@click.option('--count', default=5, help='Number of messages to sample')
def sample(queue, count):
    """Sample messages from a queue without consuming them"""
    click.echo(f"🔍 Sampling {count} messages from queue: {queue}")
    
    try:
        messages = queue_manager.get_message_sample(queue, count)
        
        if not messages:
            click.echo("📭 No messages found in queue")
            return
        
        click.echo(f"\n📨 Found {len(messages)} messages:")
        for i, msg_info in enumerate(messages, 1):
            message = msg_info['message']
            properties = msg_info['properties']
            
            click.echo(f"\n--- Message {i} ---")
            click.echo(f"ID: {message.get('message_id', 'unknown')}")
            click.echo(f"Type: {message.get('type', 'unknown')}")
            click.echo(f"Timestamp: {message.get('timestamp', 'unknown')}")
            click.echo(f"Exchange: {properties.get('exchange', '')}")
            click.echo(f"Routing Key: {properties.get('routing_key', '')}")
            
            # Show message content (truncated)
            content = json.dumps(message, indent=2)
            if len(content) > 500:
                content = content[:500] + "..."
            click.echo(f"Content: {content}")
        
    except Exception as e:
        click.echo(f"❌ Failed to sample messages: {e}")


@cli.command()
@click.option('--type', 'msg_type', required=True, 
              type=click.Choice(['social', 'scraping', 'messaging', 'test']),
              help='Message type to send')
@click.option('--platform', default='test', help='Platform name')
@click.option('--data', help='JSON data to send (optional)')
def send_test(msg_type, platform, data):
    """Send a test message"""
    click.echo(f"📤 Sending test {msg_type} message...")
    
    try:
        # Prepare test data
        test_data = {
            'test': True,
            'platform': platform,
            'timestamp': 'now',
            'content': 'This is a test message'
        }
        
        if data:
            try:
                custom_data = json.loads(data)
                test_data.update(custom_data)
            except json.JSONDecodeError:
                click.echo("❌ Invalid JSON data provided")
                return
        
        # Send message based on type
        success = False
        if msg_type == 'social':
            success = threat_producer.publish_social_media_data(test_data, platform)
        elif msg_type == 'scraping':
            success = threat_producer.publish_web_scraping_data(test_data, platform)
        elif msg_type == 'messaging':
            success = threat_producer.publish_messaging_data(test_data, platform)
        elif msg_type == 'test':
            success = threat_producer.publish_message(
                message=test_data,
                routing_key=f'test.{platform}'
            )
        
        if success:
            click.echo(f"✅ Test message sent successfully")
        else:
            click.echo(f"❌ Failed to send test message")
            
    except Exception as e:
        click.echo(f"❌ Failed to send test message: {e}")


@cli.command()
def monitor():
    """Monitor queue activity in real-time"""
    click.echo("📊 Monitoring queue activity (Press Ctrl+C to stop)...")
    
    try:
        import time
        
        while True:
            stats = queue_manager.get_queue_stats()
            
            # Clear screen (works on most terminals)
            click.clear()
            
            click.echo("📊 Real-time Queue Monitor")
            click.echo("=" * 50)
            click.echo(f"Total Messages: {stats.get('total_messages', 0)}")
            click.echo(f"Total Consumers: {stats.get('total_consumers', 0)}")
            click.echo(f"Last Update: {time.strftime('%H:%M:%S')}")
            click.echo()
            
            for queue_name, queue_stats in stats.get('queues', {}).items():
                if 'error' not in queue_stats:
                    messages = queue_stats.get('messages', 0)
                    consumers = queue_stats.get('consumers', 0)
                    status = "🟢 ACTIVE" if consumers > 0 else "🔴 IDLE" if messages > 0 else "⚪ EMPTY"
                    click.echo(f"{status} {queue_name:20} | {messages:6} msgs | {consumers:3} consumers")
            
            time.sleep(2)
            
    except KeyboardInterrupt:
        click.echo("\n👋 Monitoring stopped")
    except Exception as e:
        click.echo(f"❌ Monitoring failed: {e}")


if __name__ == "__main__":
    cli()
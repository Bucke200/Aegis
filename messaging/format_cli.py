"""
CLI utilities for message format management and testing
"""
import click
import json
import sys
import os
from typing import Dict, Any
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from messaging.schemas import MessageType, Priority, SourceType, ContentType
from messaging.message_format import (
    message_format_manager, MessageFormatUtils,
    create_social_media_message, create_web_scraping_message,
    create_messaging_message, create_threat_analysis_message,
    create_incident_alert_message, create_evidence_request_message,
    create_system_event_message
)
from messaging.test_message_format import run_format_tests, test_message_examples
from messaging.routing import message_router
from shared.logging_config import logger


@click.group()
def cli():
    """Message format management and testing commands"""
    pass


@cli.command()
def test():
    """Run comprehensive message format tests"""
    click.echo("🧪 Running message format test suite...")
    
    try:
        results = run_format_tests()
        
        if results['status'] == 'success':
            click.echo(f"\n🎉 All tests completed successfully!")
        else:
            click.echo(f"\n⚠️ Some tests failed. Please review the output above.")
        
        click.echo(f"📊 Summary: {results['passed_tests']}/{results['total_tests']} tests passed")
        
    except Exception as e:
        click.echo(f"❌ Test execution failed: {e}")


@cli.command()
def examples():
    """Test with realistic message examples"""
    click.echo("📝 Testing with realistic examples...")
    
    try:
        success = test_message_examples()
        if success:
            click.echo("✅ Realistic examples test completed successfully")
        else:
            click.echo("❌ Realistic examples test failed")
    except Exception as e:
        click.echo(f"❌ Examples test failed: {e}")


@cli.command()
@click.option('--type', 'message_type', required=True,
              type=click.Choice([t.value for t in MessageType]),
              help='Message type to create')
@click.option('--source', required=True,
              type=click.Choice([s.value for s in SourceType]),
              help='Message source')
@click.option('--priority', default='medium',
              type=click.Choice([p.value for p in Priority]),
              help='Message priority')
@click.option('--data', help='JSON data for message content')
def create(message_type, source, priority, data):
    """Create a test message"""
    click.echo(f"📝 Creating {message_type} message from {source}...")
    
    try:
        # Parse data if provided
        message_data = {}
        if data:
            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                click.echo("❌ Invalid JSON data provided")
                return
        
        # Create message based on type
        message_type_enum = MessageType(message_type)
        source_enum = SourceType(source)
        priority_enum = Priority(priority)
        
        if message_type_enum == MessageType.SOCIAL_MEDIA:
            # Default social media data
            default_data = {
                'post_id': 'cli_test_' + str(int(datetime.utcnow().timestamp())),
                'author_id': 'cli_author',
                'author_username': 'cli_user',
                'content': 'Test message created from CLI',
                'created_at': datetime.utcnow()
            }
            default_data.update(message_data)
            
            message = create_social_media_message(
                post_data=default_data,
                source=source_enum,
                priority=priority_enum
            )
            
        elif message_type_enum == MessageType.WEB_SCRAPING:
            default_data = {
                'url': 'https://example.com/cli-test',
                'title': 'CLI Test Page',
                'content': 'Test content from CLI',
                'scraped_at': datetime.utcnow()
            }
            default_data.update(message_data)
            
            message = create_web_scraping_message(
                scraping_data=default_data,
                source=source_enum,
                priority=priority_enum
            )
            
        elif message_type_enum == MessageType.MESSAGING_PLATFORM:
            default_data = {
                'message_id': 'cli_msg_' + str(int(datetime.utcnow().timestamp())),
                'channel_id': 'cli_channel',
                'author_id': 'cli_author',
                'author_username': 'cli_user',
                'content': 'Test messaging content from CLI',
                'created_at': datetime.utcnow()
            }
            default_data.update(message_data)
            
            message = create_messaging_message(
                messaging_data=default_data,
                source=source_enum,
                priority=priority_enum
            )
            
        else:
            click.echo(f"❌ Message type {message_type} not supported for CLI creation")
            return
        
        # Display created message
        click.echo("✅ Message created successfully:")
        click.echo(f"   ID: {message.message_id}")
        click.echo(f"   Type: {message.message_type}")
        click.echo(f"   Source: {message.source}")
        click.echo(f"   Priority: {message.priority}")
        
        # Show routing info
        routing = message_format_manager.get_routing_info(message)
        click.echo(f"   Routing: {routing['exchange']}.{routing['routing_key']}")
        
        # Show validation
        validation = message_format_manager.validate_message_format(message)
        if validation['valid']:
            click.echo("   Validation: ✅ Valid")
        else:
            click.echo(f"   Validation: ❌ Issues - {validation['errors']}")
        
        # Show JSON (truncated)
        json_str = message.json(indent=2)
        if len(json_str) > 500:
            json_str = json_str[:500] + "..."
        click.echo(f"\n📄 Message JSON:\n{json_str}")
        
    except Exception as e:
        click.echo(f"❌ Failed to create message: {e}")


@cli.command()
@click.option('--type', 'message_type',
              type=click.Choice([t.value for t in MessageType]),
              help='Filter by message type')
def schemas(message_type):
    """Show message schemas"""
    click.echo("📋 Message Schemas:")
    
    try:
        if message_type:
            # Show specific schema
            message_type_enum = MessageType(message_type)
            schema = message_format_manager.get_message_schema(message_type_enum)
            
            click.echo(f"\n📝 Schema for {message_type}:")
            click.echo(json.dumps(schema, indent=2))
        else:
            # Show all schemas
            schemas = MessageFormatUtils.export_message_schemas()
            
            for msg_type, schema in schemas.items():
                click.echo(f"\n📝 {msg_type}:")
                # Show just the properties for brevity
                properties = schema.get('properties', {})
                for prop_name, prop_info in properties.items():
                    prop_type = prop_info.get('type', 'unknown')
                    required = '(required)' if prop_name in schema.get('required', []) else '(optional)'
                    click.echo(f"   • {prop_name}: {prop_type} {required}")
        
    except Exception as e:
        click.echo(f"❌ Failed to show schemas: {e}")


@cli.command()
def routing():
    """Show routing configuration"""
    click.echo("🔄 Message Routing Configuration:")
    
    try:
        # Show exchange configurations
        click.echo("\n📡 Exchanges:")
        for exchange_name, config in message_router.exchange_configs.items():
            click.echo(f"   • {exchange_name} ({config['type']}): {config['description']}")
        
        # Show routing rules
        click.echo("\n📍 Routing Rules:")
        for message_type, rule in message_router.routing_rules.items():
            exchange = rule['exchange']
            template = rule['routing_key_template']
            click.echo(f"   • {message_type.value} -> {exchange}.{template}")
        
        # Show queue bindings
        click.echo("\n🔗 Recommended Queue Bindings:")
        bindings = message_router.get_queue_bindings()
        for binding in bindings[:10]:  # Show first 10
            queue = binding['queue']
            exchange = binding['exchange']
            routing_key = binding['routing_key']
            click.echo(f"   • {queue} <- {exchange}.{routing_key}")
        
        if len(bindings) > 10:
            click.echo(f"   ... and {len(bindings) - 10} more bindings")
        
        # Validate configuration
        validation = message_router.validate_routing_config()
        click.echo(f"\n✅ Routing Configuration: {'Valid' if validation['valid'] else 'Invalid'}")
        
        if validation['errors']:
            click.echo("❌ Errors:")
            for error in validation['errors']:
                click.echo(f"   • {error}")
        
        if validation['warnings']:
            click.echo("⚠️ Warnings:")
            for warning in validation['warnings']:
                click.echo(f"   • {warning}")
        
    except Exception as e:
        click.echo(f"❌ Failed to show routing configuration: {e}")


@cli.command()
def stats():
    """Show message format statistics"""
    click.echo("📊 Message Format Statistics:")
    
    try:
        stats = message_format_manager.get_format_statistics()
        
        click.echo(f"\n📈 Format Support:")
        click.echo(f"   Message Types: {stats['supported_message_types']}")
        click.echo(f"   Source Types: {stats['supported_sources']}")
        click.echo(f"   Content Types: {stats['supported_content_types']}")
        
        click.echo(f"\n🔧 Configuration:")
        click.echo(f"   Validation Rules: {stats['validation_rules_count']}")
        click.echo(f"   Routing Rules: {stats['routing_rules_count']}")
        click.echo(f"   Exchange Configs: {stats['exchange_configs_count']}")
        
        # Show supported types
        click.echo(f"\n📝 Supported Message Types:")
        for msg_type in MessageType:
            click.echo(f"   • {msg_type.value}")
        
        click.echo(f"\n📡 Supported Sources:")
        for source in SourceType:
            click.echo(f"   • {source.value}")
        
    except Exception as e:
        click.echo(f"❌ Failed to show statistics: {e}")


@cli.command()
@click.option('--file', required=True, help='JSON file containing message data')
def validate_file(file):
    """Validate messages from JSON file"""
    click.echo(f"🔍 Validating messages from {file}...")
    
    try:
        with open(file, 'r') as f:
            data = json.load(f)
        
        # Handle single message or array of messages
        messages = data if isinstance(data, list) else [data]
        
        valid_count = 0
        total_count = len(messages)
        
        for i, message_data in enumerate(messages, 1):
            try:
                # Process message
                message = message_format_manager.process_raw_message(message_data)
                
                # Validate
                validation = message_format_manager.validate_message_format(message)
                
                if validation['valid']:
                    click.echo(f"   ✅ Message {i}: Valid ({message.message_type})")
                    valid_count += 1
                else:
                    click.echo(f"   ❌ Message {i}: Invalid - {validation['errors']}")
                
            except Exception as e:
                click.echo(f"   💥 Message {i}: Failed to process - {e}")
        
        click.echo(f"\n📊 Validation Results: {valid_count}/{total_count} valid messages")
        
    except FileNotFoundError:
        click.echo(f"❌ File not found: {file}")
    except json.JSONDecodeError:
        click.echo(f"❌ Invalid JSON in file: {file}")
    except Exception as e:
        click.echo(f"❌ Validation failed: {e}")


@cli.command()
@click.option('--message-type', required=True,
              type=click.Choice([t.value for t in MessageType]),
              help='Message type to generate template for')
def template(message_type):
    """Generate message template"""
    click.echo(f"📝 Generating template for {message_type}...")
    
    try:
        message_type_enum = MessageType(message_type)
        schema = message_format_manager.get_message_schema(message_type_enum)
        
        # Generate template from schema
        template_data = {}
        
        def generate_template_value(prop_info):
            prop_type = prop_info.get('type')
            if prop_type == 'string':
                return "example_string"
            elif prop_type == 'integer':
                return 0
            elif prop_type == 'number':
                return 0.0
            elif prop_type == 'boolean':
                return False
            elif prop_type == 'array':
                return []
            elif prop_type == 'object':
                return {}
            else:
                return None
        
        properties = schema.get('properties', {})
        for prop_name, prop_info in properties.items():
            if prop_name != 'message_id':  # Skip auto-generated fields
                template_data[prop_name] = generate_template_value(prop_info)
        
        # Output template
        click.echo(f"\n📄 Template for {message_type}:")
        click.echo(json.dumps(template_data, indent=2, default=str))
        
        # Save to file
        filename = f"{message_type}_template.json"
        with open(filename, 'w') as f:
            json.dump(template_data, f, indent=2, default=str)
        
        click.echo(f"\n💾 Template saved to: {filename}")
        
    except Exception as e:
        click.echo(f"❌ Failed to generate template: {e}")


if __name__ == "__main__":
    cli()
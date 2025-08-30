"""
Elasticsearch utilities and management commands
"""
import click
from typing import Dict, Any
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from storage.elasticsearch_client import es_client
from storage.indexing_service import indexing_service
from storage.search_service import search_service
from shared.logging_config import logger


@click.group()
def cli():
    """Elasticsearch management commands"""
    pass


@cli.command()
def setup():
    """Setup Elasticsearch indices"""
    click.echo("Setting up Elasticsearch indices...")
    
    if not es_client.client:
        click.echo("❌ Failed to connect to Elasticsearch")
        return
    
    try:
        es_client.setup_indices()
        click.echo("✅ Elasticsearch indices created successfully")
    except Exception as e:
        click.echo(f"❌ Failed to setup indices: {e}")


@cli.command()
def health():
    """Check Elasticsearch health"""
    click.echo("Checking Elasticsearch health...")
    
    health_info = search_service.health_check()
    
    if health_info.get("status") == "disconnected":
        click.echo("❌ Elasticsearch is disconnected")
        return
    
    click.echo(f"✅ Cluster Status: {health_info.get('status', 'unknown')}")
    click.echo(f"📊 Cluster Name: {health_info.get('cluster_name', 'unknown')}")
    
    click.echo("\n📈 Index Statistics:")
    for index, stats in health_info.get("indices", {}).items():
        click.echo(f"  {index}: {stats['doc_count']} documents, {stats['size']} bytes")


@cli.command()
def reindex():
    """Reindex all data from database"""
    click.echo("Reindexing all data from database...")
    
    if not es_client.client:
        click.echo("❌ Failed to connect to Elasticsearch")
        return
    
    try:
        results = indexing_service.reindex_all()
        click.echo("✅ Reindexing completed:")
        for index, count in results.items():
            click.echo(f"  {index}: {count} documents indexed")
    except Exception as e:
        click.echo(f"❌ Failed to reindex: {e}")


@cli.command()
@click.option('--index', help='Index name to delete')
def delete_index(index):
    """Delete an Elasticsearch index"""
    if not index:
        click.echo("❌ Please specify an index name with --index")
        return
    
    if click.confirm(f"Are you sure you want to delete index '{index}'?"):
        try:
            if es_client.delete_index(index):
                click.echo(f"✅ Index '{index}' deleted successfully")
            else:
                click.echo(f"❌ Index '{index}' not found or failed to delete")
        except Exception as e:
            click.echo(f"❌ Failed to delete index: {e}")


@cli.command()
@click.option('--query', help='Search query')
@click.option('--limit', default=10, help='Number of results')
def search(query, limit):
    """Search incidents"""
    click.echo(f"Searching for: '{query}'")
    
    try:
        results = search_service.search_incidents(query=query, page_size=limit)
        
        click.echo(f"\n📊 Found {results.total} incidents (showing {len(results.hits)}):")
        
        for hit in results.hits:
            source = hit["_source"]
            click.echo(f"\n🔍 ID: {source['id']}")
            click.echo(f"   VIP: {source['vip_name']}")
            click.echo(f"   Platform: {source['platform']}")
            click.echo(f"   Severity: {source['severity']}")
            click.echo(f"   Type: {source['threat_type']}")
            click.echo(f"   Content: {source['content'][:100]}...")
            
            # Show highlights if available
            if "highlight" in hit:
                click.echo("   Highlights:")
                for field, highlights in hit["highlight"].items():
                    for highlight in highlights:
                        click.echo(f"     {field}: {highlight}")
    
    except Exception as e:
        click.echo(f"❌ Search failed: {e}")


@cli.command()
def stats():
    """Show incident statistics"""
    click.echo("📊 Incident Statistics:")
    
    try:
        trends = search_service.get_incident_trends(days=30)
        
        click.echo(f"\n📈 Last 30 Days:")
        click.echo(f"   Total Incidents: {trends.get('total_incidents', 0)}")
        
        click.echo(f"\n🚨 Severity Distribution:")
        for severity, count in trends.get('severity_distribution', {}).items():
            click.echo(f"   {severity}: {count}")
        
        click.echo(f"\n🎯 Threat Type Distribution:")
        for threat_type, count in trends.get('threat_type_distribution', {}).items():
            click.echo(f"   {threat_type}: {count}")
        
        click.echo(f"\n📱 Platform Distribution:")
        for platform, count in trends.get('platform_distribution', {}).items():
            click.echo(f"   {platform}: {count}")
    
    except Exception as e:
        click.echo(f"❌ Failed to get statistics: {e}")


@cli.command()
@click.option('--vip-id', required=True, help='VIP ID')
def vip_summary(vip_id):
    """Show summary for a specific VIP"""
    click.echo(f"📊 VIP Summary for: {vip_id}")
    
    try:
        summary = search_service.get_vip_summary(vip_id)
        
        click.echo(f"\n📈 Statistics:")
        click.echo(f"   Total Incidents: {summary.get('total_incidents', 0)}")
        click.echo(f"   Recent (7 days): {summary.get('recent_incidents', 0)}")
        click.echo(f"   High Severity: {summary.get('high_severity_count', 0)}")
        click.echo(f"   Unresolved: {summary.get('unresolved_count', 0)}")
        
        click.echo(f"\n📱 Platforms: {', '.join(summary.get('platforms', []))}")
        click.echo(f"🎯 Threat Types: {', '.join(summary.get('threat_types', []))}")
    
    except Exception as e:
        click.echo(f"❌ Failed to get VIP summary: {e}")


if __name__ == "__main__":
    cli()
"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create VIPs table
    op.create_table('vips',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('official_profiles', sa.JSON(), nullable=True),
        sa.Column('keywords', sa.JSON(), nullable=True),
        sa.Column('monitoring_active', sa.Boolean(), nullable=True),
        sa.Column('alert_settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vips_monitoring_active'), 'vips', ['monitoring_active'], unique=False)
    op.create_index(op.f('ix_vips_name'), 'vips', ['name'], unique=False)

    # Create Users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Create Incidents table
    op.create_table('incidents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vip_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('platform', sa.Enum('TWITTER', 'FACEBOOK', 'INSTAGRAM', 'LINKEDIN', 'TELEGRAM', 'DISCORD', 'PASTEBIN', 'GITHUB', 'MANUAL', 'SYSTEM', name='platform'), nullable=False),
        sa.Column('severity', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='severity'), nullable=False),
        sa.Column('threat_type', sa.Enum('IMPERSONATION', 'MISINFORMATION', 'THREAT', 'LEAK', 'COORDINATED_CAMPAIGN', name='threattype'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('status', sa.Enum('NEW', 'REVIEWING', 'RESOLVED', 'FALSE_POSITIVE', name='incidentstatus'), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vip_id'], ['vips.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_incidents_assigned_to'), 'incidents', ['assigned_to'], unique=False)
    op.create_index(op.f('ix_incidents_detected_at'), 'incidents', ['detected_at'], unique=False)
    op.create_index(op.f('ix_incidents_platform'), 'incidents', ['platform'], unique=False)
    op.create_index(op.f('ix_incidents_severity'), 'incidents', ['severity'], unique=False)
    op.create_index(op.f('ix_incidents_status'), 'incidents', ['status'], unique=False)
    op.create_index(op.f('ix_incidents_threat_type'), 'incidents', ['threat_type'], unique=False)
    op.create_index(op.f('ix_incidents_vip_id'), 'incidents', ['vip_id'], unique=False)

    # Create Evidence table
    op.create_table('evidence',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('screenshot_url', sa.String(length=500), nullable=True),
        sa.Column('media_urls', sa.JSON(), nullable=True),
        sa.Column('meta_data', sa.JSON(), nullable=True),
        sa.Column('source_html', sa.Text(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id')
    )

    # Create Analysis Results table
    op.create_table('analysis_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('module_name', sa.String(length=100), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_results_incident_id'), 'analysis_results', ['incident_id'], unique=False)
    op.create_index(op.f('ix_analysis_results_module_name'), 'analysis_results', ['module_name'], unique=False)

    # Create Campaigns table
    op.create_table('campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vip_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('account_count', sa.Integer(), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('network_graph', sa.JSON(), nullable=True),
        sa.Column('status', sa.Enum('NEW', 'REVIEWING', 'RESOLVED', 'FALSE_POSITIVE', name='incidentstatus'), nullable=True),
        sa.ForeignKeyConstraint(['vip_id'], ['vips.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_campaigns_detected_at'), 'campaigns', ['detected_at'], unique=False)
    op.create_index(op.f('ix_campaigns_status'), 'campaigns', ['status'], unique=False)
    op.create_index(op.f('ix_campaigns_vip_id'), 'campaigns', ['vip_id'], unique=False)

    # Create Campaign Incidents junction table
    op.create_table('campaign_incidents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'incident_id', name='unique_campaign_incident')
    )

    # Create Collected Data table
    op.create_table('collected_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source', sa.Enum('TWITTER', 'FACEBOOK', 'INSTAGRAM', 'LINKEDIN', 'TELEGRAM', 'DISCORD', 'PASTEBIN', 'GITHUB', 'MANUAL', 'SYSTEM', name='platform'), nullable=False),
        sa.Column('author', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('media_urls', sa.JSON(), nullable=True),
        sa.Column('meta_data', sa.JSON(), nullable=True),
        sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'url', 'timestamp', name='unique_collected_data')
    )
    op.create_index(op.f('ix_collected_data_collected_at'), 'collected_data', ['collected_at'], unique=False)
    op.create_index(op.f('ix_collected_data_processed'), 'collected_data', ['processed'], unique=False)
    op.create_index(op.f('ix_collected_data_source'), 'collected_data', ['source'], unique=False)
    op.create_index(op.f('ix_collected_data_timestamp'), 'collected_data', ['timestamp'], unique=False)

    # Create System Metrics table
    op.create_table('system_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('labels', sa.JSON(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_metrics_metric_name'), 'system_metrics', ['metric_name'], unique=False)
    op.create_index(op.f('ix_system_metrics_recorded_at'), 'system_metrics', ['recorded_at'], unique=False)


def downgrade() -> None:
    op.drop_table('system_metrics')
    op.drop_table('collected_data')
    op.drop_table('campaign_incidents')
    op.drop_table('campaigns')
    op.drop_table('analysis_results')
    op.drop_table('evidence')
    op.drop_table('incidents')
    op.drop_table('users')
    op.drop_table('vips')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS platform')
    op.execute('DROP TYPE IF EXISTS severity')
    op.execute('DROP TYPE IF EXISTS threattype')
    op.execute('DROP TYPE IF EXISTS incidentstatus')
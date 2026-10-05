"""Initial schema: tables, indexes, constraints, trigger, and grants.

Generated from the SQLAlchemy models; regenerate with the model metadata if
the schema changes before this migration is released.

Revision ID: 0002_initial_schema
Revises: 0001_extensions
Create Date: 2026-10-05

"""

from __future__ import annotations

from alembic import op

revision = "0002_initial_schema"
down_revision = "0001_extensions"
branch_labels = None
depends_on = None


_UPGRADE: tuple[str, ...] = (
    """CREATE TABLE accounts (
	source VARCHAR(32) NOT NULL, 
	platform_account_id TEXT NOT NULL, 
	handle TEXT, 
	display_name TEXT, 
	bio TEXT, 
	bio_embedding VECTOR(384), 
	avatar_object_key TEXT, 
	avatar_phash TEXT, 
	avatar_embedding VECTOR(512), 
	created_at_platform TIMESTAMP WITH TIME ZONE, 
	followers INTEGER, 
	following INTEGER, 
	verified BOOLEAN, 
	self_labels TEXT[] NOT NULL, 
	discovered_via VARCHAR(32) NOT NULL, 
	first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	profile_hash TEXT, 
	tsv TSVECTOR, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source, platform_account_id), 
	CONSTRAINT account_source CHECK (source IN ('replay', 'manual', 'telegram', 'github', 'x', 'facebook', 'instagram', 'youtube', 'discord', 'pastebin')), 
	CONSTRAINT discovered_via CHECK (discovered_via IN ('authored_item', 'mention', 'manual_profile', 'profile_search'))
);""",
    """CREATE TABLE alert_rules (
	scope VARCHAR(32) NOT NULL, 
	scope_id UUID, 
	min_severity VARCHAR(32) NOT NULL, 
	channels TEXT[] NOT NULL, 
	quiet_hours JSONB, 
	escalation_after INTEGER, 
	secondary_recipient TEXT, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT alert_scope CHECK (scope IN ('vip', 'user')), 
	CONSTRAINT alert_min_severity CHECK (min_severity IN ('low', 'medium', 'high', 'critical'))
);""",
    """CREATE TABLE connector_cursors (
	source VARCHAR(32) NOT NULL, 
	cursor JSONB NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	last_success_at TIMESTAMP WITH TIME ZONE, 
	stale_after_seconds INTEGER, 
	PRIMARY KEY (source), 
	CONSTRAINT cursor_source CHECK (source IN ('replay', 'manual', 'telegram', 'github', 'x', 'facebook', 'instagram', 'youtube', 'discord', 'pastebin'))
);""",
    """CREATE TABLE llm_budget_usage (
	day DATE NOT NULL, 
	tokens_used BIGINT NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (day)
);""",
    """CREATE TABLE outbox (
	event_type TEXT NOT NULL, 
	payload JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	PRIMARY KEY (id)
);""",
    """CREATE TABLE source_health (
	source VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	last_item_at TIMESTAMP WITH TIME ZONE, 
	last_error TEXT, 
	consecutive_failures INTEGER NOT NULL, 
	checked_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (source), 
	CONSTRAINT health_source CHECK (source IN ('replay', 'manual', 'telegram', 'github', 'x', 'facebook', 'instagram', 'youtube', 'discord', 'pastebin')), 
	CONSTRAINT source_health_status CHECK (status IN ('healthy', 'degraded', 'auth_failed', 'stale'))
);""",
    """CREATE TABLE users (
	email TEXT NOT NULL, 
	display_name TEXT, 
	password_hash TEXT NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	mfa_enabled BOOLEAN NOT NULL, 
	totp_secret TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	CONSTRAINT user_role CHECK (role IN ('admin', 'lead', 'analyst', 'viewer'))
);""",
    """CREATE TABLE account_edges (
	src_account_id UUID NOT NULL, 
	dst_account_id UUID NOT NULL, 
	edge_type VARCHAR(32) NOT NULL, 
	weight FLOAT NOT NULL, 
	first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (src_account_id, dst_account_id, edge_type), 
	FOREIGN KEY(src_account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(dst_account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	CONSTRAINT edge_type CHECK (edge_type IN ('reply', 'repost', 'mention', 'co_cluster'))
);""",
    """CREATE TABLE alerts (
	rule_id UUID, 
	incident_ids UUID[] NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(rule_id) REFERENCES alert_rules (id) ON DELETE SET NULL
);""",
    """CREATE TABLE audit_log (
	actor_id UUID, 
	action TEXT NOT NULL, 
	target TEXT, 
	details JSONB NOT NULL, 
	at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);""",
    """CREATE TABLE items (
	dedup_key TEXT NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	platform_item_id TEXT NOT NULL, 
	account_id UUID, 
	item_type VARCHAR(32) NOT NULL, 
	url TEXT, 
	posted_at TIMESTAMP WITH TIME ZONE, 
	collected_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	text TEXT, 
	language TEXT, 
	script TEXT, 
	ocr_text TEXT, 
	tsv TSVECTOR, 
	engagement JSONB NOT NULL, 
	scored_reach BIGINT NOT NULL, 
	relations JSONB NOT NULL, 
	raw JSONB NOT NULL, 
	removed_at TIMESTAMP WITH TIME ZONE, 
	legal_hold BOOLEAN NOT NULL, 
	schema_version TEXT NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (dedup_key), 
	CONSTRAINT item_source CHECK (source IN ('replay', 'manual', 'telegram', 'github', 'x', 'facebook', 'instagram', 'youtube', 'discord', 'pastebin')), 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE SET NULL, 
	CONSTRAINT item_type CHECK (item_type IN ('post', 'comment', 'reply', 'message', 'paste', 'code_file'))
);""",
    """CREATE TABLE saved_searches (
	user_id UUID NOT NULL, 
	name TEXT NOT NULL, 
	query JSONB NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, name), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);""",
    """CREATE TABLE scoring_configs (
	version SERIAL NOT NULL, 
	weights JSONB NOT NULL, 
	bands JSONB NOT NULL, 
	overrides JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (version), 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);""",
    """CREATE TABLE suppression_rules (
	scope VARCHAR(32) NOT NULL, 
	match JSONB NOT NULL, 
	reason TEXT, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT suppression_scope CHECK (scope IN ('vip', 'account', 'keyword', 'domain', 'global')), 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);""",
    """CREATE TABLE alert_deliveries (
	alert_id UUID NOT NULL, 
	channel VARCHAR(32) NOT NULL, 
	recipient TEXT NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	attempts INTEGER NOT NULL, 
	last_error TEXT, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	acknowledged_at TIMESTAMP WITH TIME ZONE, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(alert_id) REFERENCES alerts (id) ON DELETE CASCADE, 
	CONSTRAINT alert_channel CHECK (channel IN ('email', 'slack', 'sms')), 
	CONSTRAINT alert_delivery_status CHECK (status IN ('pending', 'sent', 'failed', 'acknowledged'))
);""",
    """CREATE TABLE item_engagement_snapshots (
	item_id UUID NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	engagement JSONB NOT NULL, 
	PRIMARY KEY (item_id, observed_at), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
);""",
    """CREATE TABLE item_versions (
	item_id UUID NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	text TEXT, 
	change_type VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE, 
	CONSTRAINT item_change_type CHECK (change_type IN ('edit', 'delete'))
);""",
    """CREATE TABLE media (
	item_id UUID, 
	content_sha256 TEXT NOT NULL, 
	object_key TEXT NOT NULL, 
	type VARCHAR(32) NOT NULL, 
	phash TEXT, 
	dhash TEXT, 
	embedding VECTOR(512), 
	first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	first_seen_item_id UUID, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE, 
	UNIQUE (content_sha256), 
	CONSTRAINT media_type CHECK (type IN ('image', 'video', 'file')), 
	FOREIGN KEY(first_seen_item_id) REFERENCES items (id) ON DELETE SET NULL
);""",
    """CREATE TABLE vips (
	name TEXT NOT NULL, 
	sensitivity VARCHAR(32) NOT NULL, 
	monitoring_active BOOLEAN NOT NULL, 
	scoring_config_version INTEGER, 
	config_version INTEGER NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT sensitivity CHECK (sensitivity IN ('low', 'normal', 'high')), 
	FOREIGN KEY(scoring_config_version) REFERENCES scoring_configs (version)
);""",
    """CREATE TABLE account_vip_scores (
	account_id UUID NOT NULL, 
	vip_id UUID NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	prescreen_score FLOAT, 
	score FLOAT, 
	components JSONB NOT NULL, 
	profile_hash TEXT, 
	vip_config_version INTEGER, 
	scored_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (account_id, vip_id), 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT score_state CHECK (state IN ('screened_out', 'pending_embeddings', 'scored', 'partial', 'stale'))
);""",
    """CREATE TABLE campaigns (
	vip_id UUID NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	account_count INTEGER NOT NULL, 
	item_count INTEGER NOT NULL, 
	coordination_score FLOAT, 
	summary TEXT, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT campaign_status CHECK (status IN ('open', 'closed'))
);""",
    """CREATE TABLE detections (
	scope VARCHAR(32) NOT NULL, 
	item_id UUID, 
	account_id UUID, 
	vip_id UUID, 
	detector TEXT NOT NULL, 
	model_version TEXT NOT NULL, 
	input_variant VARCHAR(32) NOT NULL, 
	score FLOAT NOT NULL, 
	label TEXT, 
	spans JSONB NOT NULL, 
	details JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (item_id, detector, model_version, input_variant), 
	CONSTRAINT ck_detections_scope CHECK ((scope = 'item' AND item_id IS NOT NULL AND account_id IS NULL) OR (scope = 'account' AND account_id IS NOT NULL)), 
	CONSTRAINT detection_scope CHECK (scope IN ('item', 'account')), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE, 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT input_variant CHECK (input_variant IN ('text', 'ocr_text', 'media'))
);""",
    """CREATE TABLE item_vips (
	item_id UUID NOT NULL, 
	vip_id UUID NOT NULL, 
	match_confidence FLOAT NOT NULL, 
	match_source VARCHAR(32) NOT NULL, 
	matched_value TEXT, 
	PRIMARY KEY (item_id, vip_id), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE, 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT match_source CHECK (match_source IN ('alias', 'handle', 'hashtag', 'media'))
);""",
    """CREATE TABLE official_accounts (
	vip_id UUID NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	platform_account_id TEXT NOT NULL, 
	handle TEXT, 
	display_name TEXT, 
	bio TEXT, 
	bio_embedding VECTOR(384), 
	avatar_object_key TEXT, 
	avatar_phash TEXT, 
	avatar_embedding VECTOR(512), 
	verification_evidence TEXT, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	profile_refreshed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source, platform_account_id), 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT official_source CHECK (source IN ('replay', 'manual', 'telegram', 'github', 'x', 'facebook', 'instagram', 'youtube', 'discord', 'pastebin')), 
	FOREIGN KEY(verified_by) REFERENCES users (id) ON DELETE SET NULL
);""",
    """CREATE TABLE reference_media (
	vip_id UUID NOT NULL, 
	object_key TEXT NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	phash TEXT, 
	dhash TEXT, 
	embedding VECTOR(512), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT reference_media_kind CHECK (kind IN ('portrait', 'avatar', 'official_media'))
);""",
    """CREATE TABLE sensitive_fingerprints (
	vip_id UUID NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	salted_hash TEXT NOT NULL, 
	salt_id TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT fingerprint_kind CHECK (kind IN ('phone', 'email', 'address_token', 'other'))
);""",
    """CREATE TABLE user_vip_scopes (
	user_id UUID NOT NULL, 
	vip_id UUID NOT NULL, 
	can_reveal_sensitive BOOLEAN NOT NULL, 
	PRIMARY KEY (user_id, vip_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE
);""",
    """CREATE TABLE vip_aliases (
	vip_id UUID NOT NULL, 
	alias TEXT NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	is_ambiguous BOOLEAN NOT NULL, 
	PRIMARY KEY (vip_id, alias, kind), 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT alias_kind CHECK (kind IN ('name', 'nickname', 'transliteration', 'handle', 'hashtag'))
);""",
    """CREATE TABLE vip_context_keywords (
	vip_id UUID NOT NULL, 
	keyword TEXT NOT NULL, 
	PRIMARY KEY (vip_id, keyword), 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE
);""",
    """CREATE TABLE campaign_members (
	campaign_id UUID NOT NULL, 
	member_type VARCHAR(32) NOT NULL, 
	account_id UUID, 
	item_id UUID, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_campaign_members_member_type CHECK ((member_type = 'account' AND account_id IS NOT NULL AND item_id IS NULL) OR (member_type = 'item' AND item_id IS NOT NULL AND account_id IS NULL)), 
	UNIQUE (campaign_id, item_id), 
	UNIQUE (campaign_id, account_id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE, 
	CONSTRAINT campaign_member_type CHECK (member_type IN ('account', 'item')), 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
);""",
    """CREATE TABLE incidents (
	subject_type VARCHAR(32) NOT NULL, 
	item_id UUID, 
	account_id UUID, 
	subject_vip_id UUID, 
	source VARCHAR(32) NOT NULL, 
	language TEXT, 
	risk_score FLOAT NOT NULL, 
	severity VARCHAR(32) NOT NULL, 
	severity_manual BOOLEAN NOT NULL, 
	threat_types TEXT[] NOT NULL, 
	explanation TEXT, 
	status VARCHAR(32) NOT NULL, 
	assignee_id UUID, 
	campaign_id UUID, 
	scoring_config_version INTEGER, 
	outcome VARCHAR(32), 
	source_removed BOOLEAN NOT NULL, 
	legal_hold BOOLEAN NOT NULL, 
	merged_into_id UUID, 
	below_threshold BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_incidents_subject CHECK ((subject_type = 'item' AND item_id IS NOT NULL AND account_id IS NULL AND subject_vip_id IS NULL) OR (subject_type = 'account' AND account_id IS NOT NULL AND subject_vip_id IS NOT NULL AND item_id IS NULL)), 
	CONSTRAINT ck_incidents_merged_into CHECK (merged_into_id IS NULL OR subject_type = 'item'), 
	CONSTRAINT incident_subject CHECK (subject_type IN ('item', 'account')), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE, 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(subject_vip_id) REFERENCES vips (id) ON DELETE CASCADE, 
	CONSTRAINT incident_source CHECK (source IN ('replay', 'manual', 'telegram', 'github', 'x', 'facebook', 'instagram', 'youtube', 'discord', 'pastebin')), 
	CONSTRAINT incident_severity CHECK (severity IN ('low', 'medium', 'high', 'critical')), 
	CONSTRAINT incident_status CHECK (status IN ('new', 'under_review', 'escalated', 'resolved', 'false_positive')), 
	FOREIGN KEY(assignee_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id) ON DELETE SET NULL, 
	FOREIGN KEY(scoring_config_version) REFERENCES scoring_configs (version), 
	CONSTRAINT incident_outcome CHECK (outcome IN ('reported_to_platform', 'taken_down', 'referred_to_authorities', 'no_action_needed', 'below_threshold')), 
	FOREIGN KEY(merged_into_id) REFERENCES incidents (id) ON DELETE SET NULL
);""",
    """CREATE TABLE evidence_artifacts (
	incident_id UUID NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	object_key TEXT NOT NULL, 
	sha256 TEXT NOT NULL, 
	size BIGINT NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	CONSTRAINT evidence_kind CHECK (kind IN ('raw', 'screenshot', 'html', 'media', 'account_snapshot'))
);""",
    """CREATE TABLE evidence_manifests (
	incident_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	manifest_object_key TEXT NOT NULL, 
	manifest_sha256 TEXT NOT NULL, 
	prev_manifest_sha256 TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	tsa_token TEXT, 
	PRIMARY KEY (incident_id, version), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE
);""",
    """CREATE TABLE incident_events (
	incident_id UUID NOT NULL, 
	at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	actor_id UUID, 
	event_type VARCHAR(32) NOT NULL, 
	from_value JSONB, 
	to_value JSONB, 
	reason TEXT, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT incident_event_type CHECK (event_type IN ('status_change', 'assign', 'note', 'severity_override', 'rescore', 'item_attached', 'merged_into', 'campaign_linked'))
);""",
    """CREATE TABLE incident_items (
	incident_id UUID NOT NULL, 
	item_id UUID NOT NULL, 
	attached_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	item_risk FLOAT, 
	PRIMARY KEY (incident_id, item_id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
);""",
    """CREATE TABLE incident_notes (
	incident_id UUID NOT NULL, 
	author_id UUID, 
	body TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);""",
    """CREATE TABLE incident_vips (
	incident_id UUID NOT NULL, 
	vip_id UUID NOT NULL, 
	PRIMARY KEY (incident_id, vip_id), 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	FOREIGN KEY(vip_id) REFERENCES vips (id) ON DELETE CASCADE
);""",
    """CREATE TABLE labels (
	item_id UUID, 
	incident_id UUID NOT NULL, 
	account_id UUID, 
	labeller_id UUID, 
	label VARCHAR(32) NOT NULL, 
	value TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_labels_subject CHECK ((item_id IS NOT NULL AND account_id IS NULL) OR (item_id IS NULL AND account_id IS NOT NULL)), 
	FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE, 
	FOREIGN KEY(incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(labeller_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT label_kind CHECK (label IN ('fp', 'tp', 'corrected_type', 'corrected_severity'))
);""",
    """CREATE TABLE custody_log (
	target_type VARCHAR(32) NOT NULL, 
	artifact_id UUID, 
	manifest_incident_id UUID, 
	manifest_version INTEGER, 
	actor_id UUID, 
	action VARCHAR(32) NOT NULL, 
	at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_custody_log_target CHECK ((target_type = 'artifact' AND artifact_id IS NOT NULL AND manifest_incident_id IS NULL AND manifest_version IS NULL) OR (target_type = 'manifest' AND artifact_id IS NULL AND manifest_incident_id IS NOT NULL AND manifest_version IS NOT NULL)), 
	CONSTRAINT custody_target_type CHECK (target_type IN ('artifact', 'manifest')), 
	FOREIGN KEY(artifact_id) REFERENCES evidence_artifacts (id) ON DELETE CASCADE, 
	FOREIGN KEY(manifest_incident_id) REFERENCES incidents (id) ON DELETE CASCADE, 
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT custody_action CHECK (action IN ('view', 'download', 'export'))
);""",
    """CREATE INDEX ix_accounts_avatar_embedding_hnsw ON accounts USING hnsw (avatar_embedding vector_cosine_ops);""",
    """CREATE INDEX ix_accounts_display_name_trgm ON accounts USING gin (display_name gin_trgm_ops);""",
    """CREATE INDEX ix_accounts_handle_trgm ON accounts USING gin (handle gin_trgm_ops);""",
    """CREATE INDEX ix_accounts_tsv ON accounts USING gin (tsv);""",
    """CREATE INDEX ix_outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;""",
    """CREATE INDEX ix_audit_log_at ON audit_log (at);""",
    """CREATE INDEX ix_items_language ON items (language);""",
    """CREATE INDEX ix_items_tsv ON items USING gin (tsv);""",
    """CREATE INDEX ix_media_embedding_hnsw ON media USING hnsw (embedding vector_cosine_ops);""",
    """CREATE INDEX ix_detections_account_vip ON detections (account_id, vip_id);""",
    """CREATE INDEX ix_detections_detector_created ON detections (detector, created_at);""",
    """CREATE INDEX ix_detections_item_id ON detections (item_id);""",
    """CREATE INDEX ix_official_accounts_avatar_embedding_hnsw ON official_accounts USING hnsw (avatar_embedding vector_cosine_ops);""",
    """CREATE INDEX ix_reference_media_embedding_hnsw ON reference_media USING hnsw (embedding vector_cosine_ops);""",
    """CREATE INDEX ix_incidents_campaign_id ON incidents (campaign_id);""",
    """CREATE INDEX ix_incidents_default_feed ON incidents (created_at) WHERE merged_into_id IS NULL;""",
    """CREATE INDEX ix_incidents_language ON incidents (language);""",
    """CREATE INDEX ix_incidents_severity_created ON incidents (severity, created_at);""",
    """CREATE INDEX ix_incidents_source ON incidents (source);""",
    """CREATE INDEX ix_incidents_status_assignee ON incidents (status, assignee_id);""",
    """CREATE UNIQUE INDEX uq_incidents_item ON incidents (item_id) WHERE subject_type = 'item';""",
    """CREATE UNIQUE INDEX uq_incidents_open_account ON incidents (account_id, subject_vip_id) WHERE subject_type = 'account' AND status NOT IN ('resolved', 'false_positive');""",
    """CREATE INDEX ix_incident_items_item_id ON incident_items (item_id);""",
    """CREATE OR REPLACE FUNCTION aegis_check_merged_into() RETURNS trigger AS $$
BEGIN
    IF NEW.merged_into_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM incidents
            WHERE id = NEW.merged_into_id AND subject_type = 'account'
        ) THEN
            RAISE EXCEPTION 'merged_into_id must reference an account incident';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;""",
    """CREATE TRIGGER trg_incidents_merged_into
BEFORE INSERT OR UPDATE OF merged_into_id ON incidents
FOR EACH ROW EXECUTE FUNCTION aegis_check_merged_into();""",
    """DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aegis_app') THEN
        CREATE ROLE aegis_app NOLOGIN;
    END IF;
END
$$;""",
    """GRANT SELECT, INSERT ON TABLE audit_log TO aegis_app;""",
    """REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_log FROM aegis_app;""",
    """REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_log FROM PUBLIC;""",
)


_DOWNGRADE: tuple[str, ...] = (
    """DROP TRIGGER IF EXISTS trg_incidents_merged_into ON incidents;""",
    """DROP FUNCTION IF EXISTS aegis_check_merged_into();""",
    """DROP TABLE IF EXISTS custody_log CASCADE;""",
    """DROP TABLE IF EXISTS labels CASCADE;""",
    """DROP TABLE IF EXISTS incident_vips CASCADE;""",
    """DROP TABLE IF EXISTS incident_notes CASCADE;""",
    """DROP TABLE IF EXISTS incident_items CASCADE;""",
    """DROP TABLE IF EXISTS incident_events CASCADE;""",
    """DROP TABLE IF EXISTS evidence_manifests CASCADE;""",
    """DROP TABLE IF EXISTS evidence_artifacts CASCADE;""",
    """DROP TABLE IF EXISTS incidents CASCADE;""",
    """DROP TABLE IF EXISTS campaign_members CASCADE;""",
    """DROP TABLE IF EXISTS vip_context_keywords CASCADE;""",
    """DROP TABLE IF EXISTS vip_aliases CASCADE;""",
    """DROP TABLE IF EXISTS user_vip_scopes CASCADE;""",
    """DROP TABLE IF EXISTS sensitive_fingerprints CASCADE;""",
    """DROP TABLE IF EXISTS reference_media CASCADE;""",
    """DROP TABLE IF EXISTS official_accounts CASCADE;""",
    """DROP TABLE IF EXISTS item_vips CASCADE;""",
    """DROP TABLE IF EXISTS detections CASCADE;""",
    """DROP TABLE IF EXISTS campaigns CASCADE;""",
    """DROP TABLE IF EXISTS account_vip_scores CASCADE;""",
    """DROP TABLE IF EXISTS vips CASCADE;""",
    """DROP TABLE IF EXISTS media CASCADE;""",
    """DROP TABLE IF EXISTS item_versions CASCADE;""",
    """DROP TABLE IF EXISTS item_engagement_snapshots CASCADE;""",
    """DROP TABLE IF EXISTS alert_deliveries CASCADE;""",
    """DROP TABLE IF EXISTS suppression_rules CASCADE;""",
    """DROP TABLE IF EXISTS scoring_configs CASCADE;""",
    """DROP TABLE IF EXISTS saved_searches CASCADE;""",
    """DROP TABLE IF EXISTS items CASCADE;""",
    """DROP TABLE IF EXISTS audit_log CASCADE;""",
    """DROP TABLE IF EXISTS alerts CASCADE;""",
    """DROP TABLE IF EXISTS account_edges CASCADE;""",
    """DROP TABLE IF EXISTS users CASCADE;""",
    """DROP TABLE IF EXISTS source_health CASCADE;""",
    """DROP TABLE IF EXISTS outbox CASCADE;""",
    """DROP TABLE IF EXISTS llm_budget_usage CASCADE;""",
    """DROP TABLE IF EXISTS connector_cursors CASCADE;""",
    """DROP TABLE IF EXISTS alert_rules CASCADE;""",
    """DROP TABLE IF EXISTS accounts CASCADE;""",
    """DROP ROLE IF EXISTS aegis_app;""",
)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)

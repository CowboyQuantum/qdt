-- qdt registry DDL, ddl_version 2, dialect sqlite. Generated; do not edit.

CREATE TABLE devices (
	device_id VARCHAR(255) NOT NULL, 
	kind VARCHAR(255) NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	registered_at DATETIME NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSON NOT NULL, 
	PRIMARY KEY (device_id)
);

CREATE TABLE objects (
	sha256 VARCHAR(64) NOT NULL, 
	type VARCHAR(64) NOT NULL, 
	schema_version INTEGER NOT NULL, 
	name VARCHAR(255), 
	body JSON NOT NULL, 
	PRIMARY KEY (sha256)
);

CREATE INDEX ix_objects_type_name ON objects (type, name);

CREATE TABLE registry_meta (
	"key" VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY ("key")
);

CREATE TABLE records (
	record_id VARCHAR(32) NOT NULL, 
	device_id VARCHAR(255) NOT NULL, 
	stand_id VARCHAR(255) NOT NULL, 
	stand_sha256 VARCHAR(64) NOT NULL, 
	definition_name VARCHAR(255) NOT NULL, 
	definition_sha256 VARCHAR(64) NOT NULL, 
	plan_sha256 VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(255) NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME NOT NULL, 
	outcome VARCHAR(16) NOT NULL, 
	campaign VARCHAR(255), 
	payload_path TEXT NOT NULL, 
	payload_sha256 VARCHAR(64) NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSON NOT NULL, 
	PRIMARY KEY (record_id), 
	CONSTRAINT ck_records_outcome CHECK (outcome in ('completed', 'aborted')), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id), 
	FOREIGN KEY(stand_sha256) REFERENCES objects (sha256), 
	FOREIGN KEY(definition_sha256) REFERENCES objects (sha256), 
	FOREIGN KEY(plan_sha256) REFERENCES objects (sha256)
);

CREATE INDEX ix_records_campaign ON records (campaign);

CREATE INDEX ix_records_definition ON records (definition_sha256);

CREATE INDEX ix_records_device ON records (device_id, started_at);

CREATE INDEX ix_records_stand ON records (stand_sha256);

CREATE INDEX ix_records_stand_id ON records (stand_id);

CREATE TABLE analyses (
	analysis_id VARCHAR(32) NOT NULL, 
	record_id VARCHAR(32) NOT NULL, 
	dataset_id VARCHAR(255) NOT NULL, 
	variable VARCHAR(255) NOT NULL, 
	model_name VARCHAR(255) NOT NULL, 
	scenario_kind VARCHAR(16) NOT NULL, 
	scenario_name VARCHAR(255) NOT NULL, 
	created_at DATETIME NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSON NOT NULL, 
	PRIMARY KEY (analysis_id), 
	FOREIGN KEY(record_id) REFERENCES records (record_id)
);

CREATE INDEX ix_analyses_model ON analyses (model_name, created_at);

CREATE INDEX ix_analyses_record ON analyses (record_id, created_at);

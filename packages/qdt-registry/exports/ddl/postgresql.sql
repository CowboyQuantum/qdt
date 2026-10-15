-- qdt registry DDL, ddl_version 3, dialect postgresql. Generated; do not edit.

CREATE TABLE devices (
	device_id VARCHAR(255) NOT NULL, 
	kind VARCHAR(255) NOT NULL, 
	simulated BOOLEAN NOT NULL, 
	registered_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSONB NOT NULL, 
	PRIMARY KEY (device_id)
);

CREATE TABLE objects (
	sha256 VARCHAR(64) NOT NULL, 
	type VARCHAR(64) NOT NULL, 
	schema_version INTEGER NOT NULL, 
	name VARCHAR(255), 
	body JSONB NOT NULL, 
	PRIMARY KEY (sha256)
);

CREATE INDEX ix_objects_type_name ON objects (type, name);

CREATE TABLE registry_meta (
	key VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY (key)
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
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	outcome VARCHAR(16) NOT NULL, 
	campaign VARCHAR(255), 
	payload_path TEXT NOT NULL, 
	payload_sha256 VARCHAR(64) NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSONB NOT NULL, 
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

CREATE TABLE analysis_results (
	result_id VARCHAR(32) NOT NULL, 
	record_id VARCHAR(32) NOT NULL, 
	method_name VARCHAR(255) NOT NULL, 
	method_sha256 VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSONB NOT NULL, 
	PRIMARY KEY (result_id), 
	CONSTRAINT ck_analysis_results_status CHECK (status in ('ok', 'failed')), 
	FOREIGN KEY(record_id) REFERENCES records (record_id)
);

CREATE INDEX ix_analysis_results_method ON analysis_results (method_sha256);

CREATE INDEX ix_analysis_results_record ON analysis_results (record_id, created_at);

CREATE TABLE tuning_outcomes (
	outcome_id VARCHAR(32) NOT NULL, 
	tuneup_id VARCHAR(32), 
	node_id VARCHAR(255) NOT NULL, 
	record_id VARCHAR(32), 
	result_id VARCHAR(32), 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	schema_version INTEGER NOT NULL, 
	body JSONB NOT NULL, 
	PRIMARY KEY (outcome_id), 
	CONSTRAINT ck_tuning_outcomes_status CHECK (status in ('accepted', 'rejected', 'failed')), 
	FOREIGN KEY(record_id) REFERENCES records (record_id), 
	FOREIGN KEY(result_id) REFERENCES analysis_results (result_id)
);

CREATE INDEX ix_tuning_outcomes_node ON tuning_outcomes (node_id, created_at);

CREATE INDEX ix_tuning_outcomes_tuneup ON tuning_outcomes (tuneup_id, created_at);

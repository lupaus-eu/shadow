\set ON_ERROR_STOP on

-- Local/development seed only.
-- Reads the repo-local copy of the default metamodel source.
\set metamodel_json `cat 'db/init/metamodel_state_##default##.json'`

BEGIN;

INSERT INTO users (name, role)
SELECT 'Development Admin', 'admin'
WHERE NOT EXISTS (
    SELECT 1
    FROM users
);

CREATE TEMP TABLE _seed_default_metamodel (
    metamodel_id BIGINT PRIMARY KEY,
    source_json JSONB NOT NULL
) ON COMMIT DROP;

WITH source AS (
    SELECT :'metamodel_json'::JSONB AS source_json
),
inserted_metamodel AS (
    INSERT INTO metamodels (organisation_id, version)
    SELECT NULL, (source_json ->> 'version')::INT
    FROM source
    WHERE NOT EXISTS (
        SELECT 1
        FROM metamodels
        WHERE organisation_id IS NULL
            AND deleted_time IS NULL
    )
    RETURNING metamodel_id
)
INSERT INTO _seed_default_metamodel (metamodel_id, source_json)
SELECT inserted_metamodel.metamodel_id, source.source_json
FROM inserted_metamodel
CROSS JOIN source;

INSERT INTO node_types (
    metamodel_id,
    node_type_key,
    name,
    display_name,
    ui_color,
    ui_shape,
    timeserie_id,
    timeserie_secondary_id,
    timeserie_id_rule
)
SELECT
    seed.metamodel_id,
    node_type.value ->> 'id',
    node_type.value ->> 'display_name',
    node_type.value ->> 'display_name',
    node_type.value #>> '{ui,color}',
    node_type.value #>> '{ui,shape}',
    node_type.value #>> '{timeserie,timeserie_id}',
    node_type.value #>> '{timeserie,timeserie_secundary_id}',
    node_type.value #>> '{timeserie,timeserie_id_rule}'
FROM _seed_default_metamodel AS seed
CROSS JOIN LATERAL jsonb_array_elements(seed.source_json -> 'node_types') AS node_type(value);

INSERT INTO edge_types (
    metamodel_id,
    edge_type_key,
    name,
    display_name,
    ui_style,
    ui_source_end,
    ui_target_end
)
SELECT
    seed.metamodel_id,
    edge_type.value ->> 'id',
    edge_type.value ->> 'display_name',
    edge_type.value ->> 'display_name',
    edge_type.value #>> '{ui,style}',
    edge_type.value #>> '{ui,source_end}',
    edge_type.value #>> '{ui,target_end}'
FROM _seed_default_metamodel AS seed
CROSS JOIN LATERAL jsonb_array_elements(seed.source_json -> 'edge_types') AS edge_type(value);

INSERT INTO type_attributes (
    metamodel_id,
    owner_kind,
    owner_node_type_id,
    owner_edge_type_id,
    attribute_key,
    name,
    display_name,
    data_type,
    mandatory,
    max_length,
    multiline
)
SELECT
    seed.metamodel_id,
    'node_type',
    node_types.node_type_id,
    NULL,
    attribute.value ->> 'id',
    attribute.value ->> 'display_name',
    attribute.value ->> 'display_name',
    attribute.value ->> 'data_type',
    COALESCE((attribute.value ->> 'mandatory')::BOOLEAN, FALSE),
    (attribute.value ->> 'max_length')::INT,
    (attribute.value ->> 'multiline')::BOOLEAN
FROM _seed_default_metamodel AS seed
CROSS JOIN LATERAL jsonb_array_elements(seed.source_json -> 'node_types') AS node_type(value)
JOIN node_types
    ON node_types.metamodel_id = seed.metamodel_id
    AND node_types.node_type_key = node_type.value ->> 'id'
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(node_type.value -> 'attributes', '[]'::JSONB)) AS attribute(value);

INSERT INTO type_attributes (
    metamodel_id,
    owner_kind,
    owner_node_type_id,
    owner_edge_type_id,
    attribute_key,
    name,
    display_name,
    data_type,
    mandatory,
    max_length,
    multiline
)
SELECT
    seed.metamodel_id,
    'edge_type',
    NULL,
    edge_types.edge_type_id,
    attribute.value ->> 'id',
    attribute.value ->> 'display_name',
    attribute.value ->> 'display_name',
    attribute.value ->> 'data_type',
    COALESCE((attribute.value ->> 'mandatory')::BOOLEAN, FALSE),
    (attribute.value ->> 'max_length')::INT,
    (attribute.value ->> 'multiline')::BOOLEAN
FROM _seed_default_metamodel AS seed
CROSS JOIN LATERAL jsonb_array_elements(seed.source_json -> 'edge_types') AS edge_type(value)
JOIN edge_types
    ON edge_types.metamodel_id = seed.metamodel_id
    AND edge_types.edge_type_key = edge_type.value ->> 'id'
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(edge_type.value -> 'attributes', '[]'::JSONB)) AS attribute(value);

WITH expanded_allowed_connections AS (
    SELECT
        seed.metamodel_id,
        edge_types.edge_type_id,
        source_key.value #>> '{}' AS source_node_type_key,
        target_key.value #>> '{}' AS target_node_type_key
    FROM _seed_default_metamodel AS seed
    CROSS JOIN LATERAL jsonb_array_elements(seed.source_json -> 'edge_types') AS edge_type(value)
    JOIN edge_types
        ON edge_types.metamodel_id = seed.metamodel_id
        AND edge_types.edge_type_key = edge_type.value ->> 'id'
    CROSS JOIN LATERAL jsonb_array_elements(
        COALESCE(edge_type.value -> 'allowed_connections', '[]'::JSONB)
    ) AS allowed_connection(value)
    CROSS JOIN LATERAL jsonb_array_elements(
        COALESCE(allowed_connection.value -> 'source_node_type_ids', '[]'::JSONB)
    ) AS source_key(value)
    CROSS JOIN LATERAL jsonb_array_elements(
        COALESCE(allowed_connection.value -> 'target_node_type_ids', '[]'::JSONB)
    ) AS target_key(value)
)
INSERT INTO allowed_connections (
    metamodel_id,
    edge_type_id,
    source_node_type_id,
    target_node_type_id
)
SELECT
    expanded_allowed_connections.metamodel_id,
    expanded_allowed_connections.edge_type_id,
    source_node_type.node_type_id,
    target_node_type.node_type_id
FROM expanded_allowed_connections
JOIN node_types AS source_node_type
    ON source_node_type.metamodel_id = expanded_allowed_connections.metamodel_id
    AND source_node_type.node_type_key = expanded_allowed_connections.source_node_type_key
JOIN node_types AS target_node_type
    ON target_node_type.metamodel_id = expanded_allowed_connections.metamodel_id
    AND target_node_type.node_type_key = expanded_allowed_connections.target_node_type_key;

COMMIT;

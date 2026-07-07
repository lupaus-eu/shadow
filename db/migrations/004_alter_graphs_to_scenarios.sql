-- Remove the legacy graphs table and attach graph_nodes/graph_edges directly to scenarios.
-- This migration preserves existing relationships by backfilling scenario_id from graphs -> org_states -> scenarios.

ALTER TABLE graph_nodes
    ADD COLUMN scenario_id BIGINT,
    ADD COLUMN name TEXT,
    ADD COLUMN description TEXT;

ALTER TABLE graph_edges
    ADD COLUMN scenario_id BIGINT,
    ADD COLUMN name TEXT,
    ADD COLUMN description TEXT;

-- `graphs.org_state_id` links to org_states; use the existing org_state -> scenario relationship.
UPDATE graph_nodes gn
SET scenario_id = os.scenario_id,
    name = COALESCE(gn.name, gn.node_key)
FROM graphs g
JOIN org_states os ON g.org_state_id = os.org_state_id
WHERE gn.graph_id = g.graph_id;

UPDATE graph_edges ge
SET scenario_id = os.scenario_id,
    name = COALESCE(ge.name, ge.edge_key)
FROM graphs g
JOIN org_states os ON g.org_state_id = os.org_state_id
WHERE ge.graph_id = g.graph_id;

ALTER TABLE graph_nodes
    ALTER COLUMN scenario_id SET NOT NULL,
    ALTER COLUMN name SET NOT NULL,
    ALTER COLUMN create_date SET NOT NULL;

ALTER TABLE graph_edges
    ALTER COLUMN scenario_id SET NOT NULL,
    ALTER COLUMN name SET NOT NULL,
    ALTER COLUMN create_date SET NOT NULL;

ALTER TABLE graph_nodes
    ADD CONSTRAINT fk_graph_nodes_scenario
    FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id) ON DELETE CASCADE;

ALTER TABLE graph_edges
    ADD CONSTRAINT fk_graph_edges_scenario
    FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id) ON DELETE CASCADE;

ALTER TABLE graph_nodes DROP COLUMN graph_id;
ALTER TABLE graph_edges DROP COLUMN graph_id;

DROP INDEX IF EXISTS ux_graphs_org_state_active;
DROP INDEX IF EXISTS idx_graph_nodes_graph_active;
DROP INDEX IF EXISTS idx_graph_nodes_graph_type_active;
DROP INDEX IF EXISTS ux_graph_nodes_graph_key_active;
DROP INDEX IF EXISTS idx_graph_edges_graph_active;
DROP INDEX IF EXISTS idx_graph_edges_graph_type_active;
DROP INDEX IF EXISTS ux_graph_edges_graph_key_active;

CREATE INDEX idx_graph_nodes_scenario_active
    ON graph_nodes (scenario_id)
    WHERE deleted_time IS NULL;

CREATE INDEX idx_graph_nodes_scenario_type_active
    ON graph_nodes (scenario_id, node_type_id)
    WHERE deleted_time IS NULL;

CREATE INDEX idx_graph_nodes_scenario_create_date_active
    ON graph_nodes (scenario_id, create_date)
    WHERE deleted_time IS NULL;

CREATE UNIQUE INDEX ux_graph_nodes_scenario_key_active
    ON graph_nodes (scenario_id, node_key)
    WHERE deleted_time IS NULL;

CREATE INDEX idx_graph_edges_scenario_active
    ON graph_edges (scenario_id)
    WHERE deleted_time IS NULL;

CREATE INDEX idx_graph_edges_scenario_type_active
    ON graph_edges (scenario_id, edge_type_id)
    WHERE deleted_time IS NULL;

CREATE INDEX idx_graph_edges_scenario_create_date_active
    ON graph_edges (scenario_id, create_date)
    WHERE deleted_time IS NULL;

CREATE UNIQUE INDEX ux_graph_edges_scenario_key_active
    ON graph_edges (scenario_id, edge_key)
    WHERE deleted_time IS NULL;

DROP TABLE graphs;

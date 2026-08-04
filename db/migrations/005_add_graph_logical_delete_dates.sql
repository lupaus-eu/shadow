-- Add logical lifetime end dates while retaining deleted_time for persistence soft deletion.

ALTER TABLE graph_nodes
    ADD COLUMN delete_date DATE,
    ADD CONSTRAINT ck_graph_nodes_lifetime
        CHECK (delete_date IS NULL OR delete_date >= create_date);

ALTER TABLE graph_edges
    ADD COLUMN delete_date DATE,
    ADD CONSTRAINT ck_graph_edges_lifetime
        CHECK (delete_date IS NULL OR delete_date >= create_date);

CREATE INDEX idx_graph_nodes_scenario_lifetime_active
    ON graph_nodes (scenario_id, create_date, delete_date)
    WHERE deleted_time IS NULL;

CREATE INDEX idx_graph_edges_scenario_lifetime_active
    ON graph_edges (scenario_id, create_date, delete_date)
    WHERE deleted_time IS NULL;

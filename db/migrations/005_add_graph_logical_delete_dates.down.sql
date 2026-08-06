DROP INDEX idx_graph_nodes_scenario_lifetime_active;
DROP INDEX idx_graph_edges_scenario_lifetime_active;

ALTER TABLE graph_nodes
    DROP CONSTRAINT ck_graph_nodes_lifetime,
    DROP COLUMN delete_date;

ALTER TABLE graph_edges
    DROP CONSTRAINT ck_graph_edges_lifetime,
    DROP COLUMN delete_date;

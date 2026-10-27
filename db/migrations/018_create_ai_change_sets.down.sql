-- Destructive for every AI change set, its operations, frozen values and
-- review history. Business rows created by applied change sets stay.
DROP TABLE ai_change_set_operations;
DROP TABLE ai_change_sets;

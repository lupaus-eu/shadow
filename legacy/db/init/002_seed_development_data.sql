\set ON_ERROR_STOP on

-- Local/development seed only.
-- Reads the repo-local copy of the default metamodel source.
\set metamodel_json `cat 'db/init/metamodel_state_##default##.json'`

BEGIN;

INSERT INTO users (name, email, role)
SELECT seed.name, seed.email, seed.role
FROM (
    VALUES
        ('Development Consultant', 'consultant@example.local', 'consultant'),
        ('Development Admin', 'admin@example.local', 'admin')
) AS seed(name, email, role)
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE lower(trim(users.email)) = lower(seed.email)
        AND users.deleted_time IS NULL
);

SELECT set_config(
    'shadow.seed_reference_data.metamodel_json',
    :'metamodel_json',
    true
);

\i db/init/001_seed_reference_data.sql

COMMIT;

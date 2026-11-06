ALTER TABLE auth_sessions
    DROP CONSTRAINT ck_auth_sessions_id_token_non_blank,
    DROP COLUMN id_token;

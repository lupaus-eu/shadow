-- ADR-017: the ID token of a sign-in is kept with its session only to send id_token_hint
-- when the person signs out, so that Authentik's session ends as well. It is deleted with
-- the session. Existing sessions have none and sign out of Shadow only.
ALTER TABLE auth_sessions
    ADD COLUMN id_token TEXT,
    ADD CONSTRAINT ck_auth_sessions_id_token_non_blank
        CHECK (id_token IS NULL OR id_token ~ '[^[:space:]]');

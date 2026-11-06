DROP TABLE auth_sessions;
DROP TABLE oidc_login_transactions;
DROP TABLE user_identities;

DROP INDEX ux_users_email_active;

ALTER TABLE users
    DROP COLUMN email;

ALTER TABLE users
    DROP CONSTRAINT ck_users_locale,
    DROP CONSTRAINT ck_users_account_class,
    DROP COLUMN locale,
    DROP COLUMN account_class;

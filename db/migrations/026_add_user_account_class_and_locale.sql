-- ADR-016/ADR-017: an account is either a customer account (signs in to the application)
-- or a platform account (an operator, only for the platform console, step 7), and has a
-- language for text built for the person. Existing users become customers with English.
ALTER TABLE users
    ADD COLUMN account_class TEXT NOT NULL DEFAULT 'customer',
    ADD COLUMN locale TEXT NOT NULL DEFAULT 'en',
    ADD CONSTRAINT ck_users_account_class CHECK (account_class IN ('customer', 'platform')),
    ADD CONSTRAINT ck_users_locale CHECK (locale IN ('fi', 'en'));

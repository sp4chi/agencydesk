-- DEV/TEST ONLY. Gives the app's two login roles a password so they can
-- connect over TCP to the Docker Postgres. Run by `make db-reset` and the
-- test suite. Never run this in production: set real passwords there via
-- your secret manager. schema.sql deliberately contains no passwords.
ALTER ROLE agencydesk_api  PASSWORD 'dev-api-password';
ALTER ROLE agencydesk_auth PASSWORD 'dev-auth-password';

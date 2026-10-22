-- The registry server's three roles (ADR 0074; Analysis 0003 §6): qdt_admin creates the tables (once,
-- `python -m qdt_registry init`), qdt_writer is what stand servers sync as, qdt_reader is what the read
-- server and every script read as. Run once as the Postgres superuser, with the passwords on the command
-- line and never in a file that is committed:
--
--   psql -U postgres -d postgres -v db=qdt -v admin_pw='...' -v writer_pw='...' -v reader_pw='...' -f roles.sql
--
-- CI runs the same file against its ephemeral `qdt_test` (.github/workflows/ci.yml).
CREATE ROLE qdt_admin LOGIN PASSWORD :'admin_pw';
CREATE ROLE qdt_writer LOGIN PASSWORD :'writer_pw';
CREATE ROLE qdt_reader LOGIN PASSWORD :'reader_pw';
GRANT CONNECT ON DATABASE :"db" TO qdt_admin, qdt_writer, qdt_reader;
\connect :"db"
GRANT USAGE, CREATE ON SCHEMA public TO qdt_admin;
GRANT USAGE ON SCHEMA public TO qdt_writer, qdt_reader;
-- tables the admin creates from now on: the writer inserts (rows are never updated, ADR 0026), the reader selects
ALTER DEFAULT PRIVILEGES FOR ROLE qdt_admin IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO qdt_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE qdt_admin IN SCHEMA public GRANT SELECT ON TABLES TO qdt_reader;
-- tables that already exist (a server initialised before this file ran)
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO qdt_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO qdt_reader;

import pg from "pg";

const pool = new pg.Pool({
  connectionString:
    process.env["DATABASE_SYNC_URL"] ??
    "postgresql://postgres:postgres@localhost:5432/complianceforge",
});

export default pool;

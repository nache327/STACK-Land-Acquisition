import psycopg2

from scripts._db import get_sync_dsn

conn = psycopg2.connect(get_sync_dsn())
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM competitor_facilities")
print("Total rows:", cur.fetchone()[0])
cur.execute("SELECT data_source, COUNT(*) FROM competitor_facilities GROUP BY data_source")
print("By source:", cur.fetchall())
conn.close()

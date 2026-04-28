import psycopg2
conn = psycopg2.connect("postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres")
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM competitor_facilities")
print("Total rows:", cur.fetchone()[0])
cur.execute("SELECT data_source, COUNT(*) FROM competitor_facilities GROUP BY data_source")
print("By source:", cur.fetchall())
conn.close()

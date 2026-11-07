"""Print schema and wait diagnostics, never connection credentials."""
import json,psycopg
from pathlib import Path
root=Path(__file__).resolve().parents[1]
value=next(line.partition('=')[2] for line in (root/'.env.vercel.production').read_text().splitlines() if line.startswith('DATABASE_URL='))
with psycopg.connect(json.loads(value),connect_timeout=12) as connection:
    print(connection.execute("select state,wait_event_type,wait_event,left(query,160) from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid()").fetchall())
    print(connection.execute("select table_name from information_schema.tables where table_schema=current_schema() order by table_name").fetchall())

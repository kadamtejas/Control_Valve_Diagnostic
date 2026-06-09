"""
seed_readings.py
Reads My_plant_data_1.xlsx Sheet1 and bulk-inserts all
57,600 minutewise tag readings into ValveDiagnosticDB.tag_readings.

Run after rebuild_db.sql:
    cd D:\desktop\Ingenero\Valve_Diagnostic_Tool_POC\database
    python seed_readings.py

Requirements:
    pip install pyodbc openpyxl
"""

import os
import sys
import time
import pyodbc
import openpyxl

# ── Config ────────────────────────────────────────────────────
SERVER   = r"TEJAS-KADAM\SQLEXPRESS"
DATABASE = "ValveDiagnosticDB"
EXCEL    = os.path.join(os.path.dirname(__file__), '..', 'My_plant_data_1.xlsx')
BATCH    = 1000

# ── Connect ───────────────────────────────────────────────────
print(f"Connecting to {SERVER} ...")
conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
)
conn.autocommit = False
cursor = conn.cursor()
print("Connected.\n")

# ── Load tag_id map from DB ───────────────────────────────────
cursor.execute("SELECT tag_name, id FROM tags")
tag_id_map = {row[0]: row[1] for row in cursor.fetchall()}
print(f"Loaded {len(tag_id_map)} tags from DB.")

# ── Read Excel ────────────────────────────────────────────────
print(f"Reading Excel ...")
wb   = openpyxl.load_workbook(EXCEL, data_only=True, read_only=True)
ws   = wb['Sheet1']
rows = list(ws.iter_rows(values_only=True))
wb.close()

header    = rows[0]
data_rows = rows[1:]
print(f"Sheet1: {len(data_rows)} data rows x {len(header)} columns.\n")

# Map column index → tag_id
# Excel tag names are case-sensitive (mode/Mode), match exactly to DB
col_to_tag = {}
missing    = []
for i, col in enumerate(header):
    if col is None or col == 'TIMESTAMP':
        continue
    if col in tag_id_map:
        col_to_tag[i] = tag_id_map[col]
    else:
        missing.append(col)

if missing:
    print(f"WARNING: {len(missing)} Excel columns not found in tags table:")
    for m in missing:
        print(f"  {m}")
    print()

print(f"Matched {len(col_to_tag)} tag columns.\n")

# ── Build insert rows ─────────────────────────────────────────
print("Building rows ...")
insert_rows = []

for row in data_rows:
    ts = row[0]
    if ts is None:
        continue
    for col_idx, tag_id in col_to_tag.items():
        val = row[col_idx]
        # MODE columns contain strings like 'Auto' — store as NULL float
        # The mode_mapping table handles string→category translation
        if isinstance(val, str):
            try:
                val = float(val)
            except ValueError:
                val = None
        insert_rows.append((tag_id, ts, val, 'GOOD', 'My_plant_data_1'))

total = len(insert_rows)
print(f"Total rows to insert: {total:,}\n")

# ── Bulk insert ───────────────────────────────────────────────
sql = """
INSERT INTO tag_readings (tag_id, recorded_at, value, quality, source)
VALUES (?, ?, ?, ?, ?)
"""

inserted = 0
t_start  = time.time()

for i in range(0, total, BATCH):
    batch = insert_rows[i : i + BATCH]
    cursor.executemany(sql, batch)
    conn.commit()
    inserted += len(batch)

    elapsed = time.time() - t_start
    pct     = inserted / total * 100
    rate    = inserted / elapsed if elapsed > 0 else 0
    eta     = (total - inserted) / rate if rate > 0 else 0
    print(f"  {inserted:>7,} / {total:,}  ({pct:.1f}%)  "
          f"{rate:.0f} rows/s  ETA {eta:.0f}s     ", end='\r')

elapsed = time.time() - t_start
print(f"\n\nDone. Inserted {inserted:,} rows in {elapsed:.1f}s.")
cursor.close()
conn.close()

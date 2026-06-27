"""수집 결과 검증 - Step B"""
import sys
import pathlib
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

raw_dir = pathlib.Path(__file__).parent.parent / "backend" / "data" / "raw"

print("=== raw 파일 현황 ===")
total = 0
for f in sorted(raw_dir.glob("*.parquet")):
    df = pd.read_parquet(f)
    print(f"{f.name}: {len(df)}건")
    print(f"  columns: {list(df.columns)}")
    print(f"  source: {df['source'].unique()}")
    print(f"  rating range: {df['rating'].min()}-{df['rating'].max()}")
    print(f"  sample text: {df['review_text'].iloc[0][:60]}")
    total += len(df)

print(f"\n총 수집량: {total}건 (목표: 1,000건 이상)")
if total >= 1000:
    print("성공 기준 달성!")
else:
    print(f"미달 — {1000 - total}건 추가 필요")

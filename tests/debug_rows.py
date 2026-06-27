import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd

raw = pd.read_parquet('backend/data/raw/google_play_com.shinhan.sbanking_20260620.parquet')
proc = pd.read_parquet('backend/data/processed/com.shinhan.sbanking_processed.parquet')
print('raw rows:', len(raw))
print('processed rows:', len(proc))
print('raw rating dist:', raw['rating'].value_counts().sort_index().to_dict())
if 'is_short' in proc.columns:
    print('is_short count:', proc['is_short'].sum())

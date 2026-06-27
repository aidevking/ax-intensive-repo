"""F1 개선을 위한 디버그 분석"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pandas as pd
import numpy as np
from backend.services.analyze_service import AnalyzeService

svc = AnalyzeService()
df = svc.preprocess('com.shinhan.sbanking', force=True)
df = svc.label_reviews(df)

# 클래스 분포 확인
print("=== 전체 라벨 분포 ===")
print(df['sentiment_label'].value_counts())
print(f"\n총 {len(df)}건 중 is_short={df.is_short.sum()}건 제외하면 {len(df[~df.is_short])}건")

# 중립 리뷰 샘플 확인
print("\n=== 중립(neutral) 리뷰 샘플 ===")
neutral_df = df[df['sentiment_label'] == 'neutral']
print(f"중립 리뷰 수: {len(neutral_df)}")
for _, row in neutral_df.head(5).iterrows():
    print(f"  [{row['rating']}점] {row['review_text'][:80]}")

# is_short 제외 후 분포
df_train = df[~df['is_short']]
print(f"\n=== 학습 데이터 (is_short 제외) 라벨 분포 ===")
print(df_train['sentiment_label'].value_counts())

# 중립 리뷰가 너무 적은 경우 stratify 문제 확인
from sklearn.model_selection import train_test_split
labels = df_train['sentiment_label'].tolist()
print(f"\n중립 클래스 수: {labels.count('neutral')}")
print(f"train split 후 test neutral 예상: {int(labels.count('neutral') * 0.2)}")

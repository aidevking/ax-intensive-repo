import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

print("imports...", flush=True)
from backend.services.analyze_service import AnalyzeService
print("AnalyzeService imported", flush=True)

svc = AnalyzeService()
APP_ID = "com.shinhan.sbanking"

print("=== 전처리 ===", flush=True)
df = svc.preprocess(APP_ID, force=True)
print(f"전처리 완료: {len(df)}건, is_short={df.is_short.sum()}건", flush=True)

print("=== 라벨링 ===", flush=True)
df_labeled = svc.label_reviews(df)
pos = len(df_labeled[df_labeled.sentiment_label == "positive"])
neg = len(df_labeled[df_labeled.sentiment_label == "negative"])
neu = len(df_labeled[df_labeled.sentiment_label == "neutral"])
print(f"positive={pos}, negative={neg}, neutral={neu}", flush=True)
print(f"불일치: {df_labeled.is_mismatch.sum()}건", flush=True)

print("=== 모델 학습 ===", flush=True)
metrics = svc.train_model(APP_ID)
print(f"macro F1: {metrics['f1']:.4f}", flush=True)
print(f"precision: {metrics['precision']:.4f}", flush=True)
print(f"recall: {metrics['recall']:.4f}", flush=True)

cr = metrics['class_report']
for cls in ["positive", "negative", "neutral"]:
    r = cr.get(cls, {})
    print(f"  {cls}: p={r.get('precision',0):.3f} r={r.get('recall',0):.3f} f1={r.get('f1-score',0):.3f} sup={r.get('support',0)}", flush=True)

print(f"\n오분류 케이스: {len(metrics['misclassified_cases'])}건", flush=True)
for case in metrics['misclassified_cases']:
    print(f"  [{case['true_label']}→{case['predicted_label']}] r={case.get('rating','?')} | {case['review_text'][:60]}", flush=True)
    print(f"    원인: {case['cause'][:80]}", flush=True)

print("\n=== 토픽 모델링 ===", flush=True)
topics = svc.get_topics(APP_ID)
print(f"토픽 수: {len(topics)}", flush=True)
for t in topics:
    print(f"  [{t['topic_name']}] kw={t['keywords'][:4]} cnt={t['count']}", flush=True)

print("\n=== EDA ===", flush=True)
eda = svc.get_eda(APP_ID)
print(f"total={eda['total_reviews']}, avg_rating={eda['avg_rating']}", flush=True)
print(f"sentiment={eda['sentiment_distribution']}", flush=True)
print(f"short_count={eda['short_review_count']}", flush=True)
print("DONE", flush=True)

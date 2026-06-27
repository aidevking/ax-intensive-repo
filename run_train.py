import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

print("imports...")
from backend.services.analyze_service import AnalyzeService
print("AnalyzeService imported")

svc = AnalyzeService()

print("=== 전처리 (force=True) ===")
df = svc.preprocess('com.shinhan.sbanking', force=True)
print(f"전처리 완료: {len(df)}건, is_short={df.is_short.sum()}건")

print("=== 라벨링 ===")
df = svc.label_reviews(df)
pos = len(df[df.sentiment_label=='positive'])
neg = len(df[df.sentiment_label=='negative'])
neu = len(df[df.sentiment_label=='neutral'])
print(f"positive={pos}, negative={neg}, neutral={neu}")
print(f"불일치: {df.is_mismatch.sum()}건")

print("=== 모델 학습 ===")
metrics = svc.train_model('com.shinhan.sbanking')
print(f"macro F1: {metrics['f1']:.4f}")
print(f"precision: {metrics['precision']:.4f}")
print(f"recall: {metrics['recall']:.4f}")
cr = metrics['class_report']
for cls in ['positive', 'negative', 'neutral']:
    if cls in cr:
        c = cr[cls]
        print(f"  {cls}: p={c['precision']:.3f} r={c['recall']:.3f} f1={c['f1-score']:.3f} sup={c['support']}")

print(f"\n오분류 케이스: {len(metrics['misclassified_cases'])}건")
for case in metrics['misclassified_cases'][:5]:
    print(f"  [{case['true_label']}→{case['predicted_label']}] r={case['rating']} | {case['review_text'][:60]}")
    print(f"    원인: {case['cause']}")
print("DONE")

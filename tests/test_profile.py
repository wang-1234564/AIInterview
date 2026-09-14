from sqlalchemy import func, select

from app.models import Answer, Interview, ProfileSnapshot
from app.services.profile import (
    aggregate_categories,
    compute_profile,
    identify_weak_categories,
    save_snapshot,
    total_stats,
)


def test_aggregate_and_weak(db):
    iv = Interview(status="completed")
    db.add(iv)
    db.flush()
    for category, score in [("Java", 80), ("Java", 90), ("Algo", 40), ("Net", 70)]:
        db.add(
            Answer(
                interview_id=iv.id,
                category=category,
                question="q",
                standard_answer="a",
                user_answer="u",
                score=float(score),
            )
        )
    db.commit()

    cats = aggregate_categories(db)
    assert cats[0]["category"] == "Algo"
    assert cats[0]["avg_score"] == 40.0
    assert cats[-1]["category"] == "Java"
    assert cats[-1]["avg_score"] == 85.0

    weak = identify_weak_categories(cats)
    assert [w["category"] for w in weak] == ["Algo"]

    stats = total_stats(db)
    assert stats["answered"] == 4
    assert stats["interviews"] == 1
    assert stats["avg_all"] == 70.0


def test_weak_fallback_when_all_above_threshold(db):
    iv = Interview(status="completed")
    db.add(iv)
    db.flush()
    for category, score in [("Java", 85), ("Net", 75)]:
        db.add(
            Answer(
                interview_id=iv.id,
                category=category,
                question="q",
                standard_answer="a",
                user_answer="u",
                score=float(score),
            )
        )
    db.commit()

    cats = aggregate_categories(db)
    weak = identify_weak_categories(cats)
    assert [w["category"] for w in weak] == ["Net"]


def test_empty_profile(db):
    assert aggregate_categories(db) == []
    assert identify_weak_categories([]) == []
    assert total_stats(db) == {"answered": 0, "interviews": 0, "avg_all": None}


def _count_snapshots(db) -> int:
    return db.execute(select(func.count(ProfileSnapshot.id))).scalar() or 0


def test_compute_profile_has_no_side_effect(db):
    """compute_profile 只计算，不写数据库（GET 接口无副作用）。"""
    compute_profile(db)
    assert _count_snapshots(db) == 0


def test_snapshot_only_keeps_latest(db):
    content = compute_profile(db)
    for _ in range(5):
        save_snapshot(db, content)
    assert _count_snapshots(db) == 5

    # 上限设为 3 时，只保留最近 3 条
    save_snapshot(db, content, keep=3)
    assert _count_snapshots(db) == 3

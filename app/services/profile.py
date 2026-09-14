"""用户画像：按板块聚合得分、识别薄弱板块、生成学习建议（可保存快照）。"""
import json
from typing import List

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Answer, Interview, ProfileSnapshot
from app.services.deepseek import DeepSeekClient, DeepSeekError
from app.services.llm_config import LLMConfig, resolve_config


def aggregate_categories(db: Session) -> List[dict]:
    """按板块（category）聚合平均贴合度与答题数，按平均分升序。"""
    rows = db.execute(
        select(
            Answer.category,
            func.avg(Answer.score),
            func.count(Answer.id),
        )
        .where(Answer.score.isnot(None))
        .group_by(Answer.category)
        .order_by(func.avg(Answer.score))
    ).all()
    return [
        {"category": cat or "未分类", "avg_score": round(float(avg), 1), "count": cnt}
        for cat, avg, cnt in rows
    ]


def total_stats(db: Session) -> dict:
    answered = db.execute(select(func.count(Answer.id))).scalar() or 0
    interviews = db.execute(select(func.count(Interview.id))).scalar() or 0
    avg_all = db.execute(
        select(func.avg(Answer.score)).where(Answer.score.isnot(None))
    ).scalar()
    return {
        "answered": answered,
        "interviews": interviews,
        "avg_all": round(float(avg_all), 1) if avg_all is not None else None,
    }


def identify_weak_categories(categories: List[dict]) -> List[dict]:
    """识别薄弱板块：平均分 < 60 者；若均达标，取平均分最低（并列时取答题少）的板块。"""
    weak = [c for c in categories if c["avg_score"] < 60]
    if not weak and categories:
        weakest = min(categories, key=lambda c: (c["avg_score"], c["count"]))
        weak = [weakest]
    return weak


def build_advice_messages(
    categories: List[dict], weak: List[dict], stats: dict
) -> List[dict]:
    cat_lines = "\n".join(
        f"- {c['category']}：平均 {c['avg_score']} 分，答题 {c['count']} 次"
        for c in categories
    ) or "（暂无数据）"
    weak_lines = (
        "\n".join(f"- {c['category']}（平均 {c['avg_score']} 分）" for c in weak)
        or "（无明显薄弱板块）"
    )
    system = (
        "你是一位学习教练。请根据用户各知识板块的面试得分与答题量，"
        "明确指出薄弱板块，并给出具体、可执行的学习优化建议（复习方向、方法、优先级）。"
        "用中文输出，200 字左右，直接输出正文，不要列标题。"
    )
    user = (
        f"用户总体情况：累计答题 {stats['answered']} 题，参加 {stats['interviews']} 次面试，"
        f"总平均贴合度 {stats['avg_all']} 分。\n"
        f"各板块表现：\n{cat_lines}\n"
        f"薄弱板块：\n{weak_lines}\n"
        "请给出学习优化建议。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _mock_advice(
    categories: List[dict], weak: List[dict], stats: dict
) -> str:
    if not categories:
        return "暂无答题记录。请先进行模拟面试，系统将根据每次回答分析你的薄弱板块并给出学习建议。"
    if weak:
        names = "、".join(c["category"] for c in weak)
        text = f"当前薄弱板块：{names}。建议优先复习这些板块的基础概念，并针对薄弱点多做专项练习，逐步提升贴合度。"
    else:
        text = "各板块表现较为均衡，建议保持练习节奏并逐步提升题目难度。"
    text += "（mock 模式）配置 DEEPSEEK_API_KEY 后可获得更个性化的学习建议。"
    return text


ADVICE_MAX_TOKENS = 1600


def generate_advice(
    categories: List[dict], weak: List[dict], stats: dict, llm: LLMConfig
) -> dict:
    """生成学习优化建议。

    返回 {text, source, warning}；降级时会带上 warning 供前端提示。
    """
    warning = ""
    if llm.enabled:
        client = DeepSeekClient(llm)
        try:
            text = client.chat(
                build_advice_messages(categories, weak, stats),
                temperature=0.5,
                max_tokens=ADVICE_MAX_TOKENS,
            )
            if text.strip():
                return {"text": text.strip(), "source": "llm", "warning": ""}
            warning = "大模型未返回有效内容，本建议由本地规则生成。"
        except DeepSeekError as exc:
            warning = f"大模型调用失败，本建议由本地规则生成：{exc}"
    return {
        "text": _mock_advice(categories, weak, stats),
        "source": "mock",
        "warning": warning,
    }


MAX_SNAPSHOTS = 50


def save_snapshot(
    db: Session, content: dict, keep: int = MAX_SNAPSHOTS
) -> ProfileSnapshot:
    """保存画像快照，并只保留最近 keep 条，避免快照表无限增长。"""
    snap = ProfileSnapshot(content=json.dumps(content, ensure_ascii=False, default=str))
    db.add(snap)
    db.flush()
    stale_ids = db.execute(
        select(ProfileSnapshot.id).order_by(ProfileSnapshot.id.desc()).offset(keep)
    ).scalars().all()
    if stale_ids:
        db.execute(delete(ProfileSnapshot).where(ProfileSnapshot.id.in_(stale_ids)))
    db.commit()
    db.refresh(snap)
    return snap


def compute_profile(db: Session) -> dict:
    """计算完整画像（聚合 + 薄弱项 + 建议）。

    只做查询与计算、不写数据库，因此可以安全地由 GET 接口调用。
    """
    categories = aggregate_categories(db)
    weak = identify_weak_categories(categories)
    stats = total_stats(db)
    llm = resolve_config(db)
    advice = generate_advice(categories, weak, stats, llm)
    return {
        "categories": categories,
        "weak": weak,
        "stats": stats,
        "advice": advice["text"],
        "advice_source": advice["source"],
        "advice_warning": advice["warning"],
    }

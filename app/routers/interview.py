"""面试路由：创建会话并抽题、逐题提交回答并评估、结束会话、历史记录。"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Answer, Interview, KnowledgeItem
from app.services.draw import draw_questions
from app.services.evaluator import evaluate_answer
from app.services.llm_config import resolve_config
from app.services.report import build_report

router = APIRouter(prefix="/api/interview", tags=["interview"])


class InterviewCreate(BaseModel):
    company: Optional[str] = None
    category: Optional[str] = None
    count: int = 5


class AnswerSubmit(BaseModel):
    knowledge_item_id: int
    answer: str


@router.post("/create")
def create_interview(payload: InterviewCreate, db: Session = Depends(get_db)):
    """按公司/类别/数量抽题并创建面试会话。"""
    questions = draw_questions(
        db, company=payload.company, category=payload.category, count=payload.count
    )
    if not questions:
        raise HTTPException(400, "没有符合条件的题目，请先在题库中导入")

    interview = Interview(status="in_progress")
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return {
        "interview_id": interview.id,
        "questions": [
            {
                "id": q.id,
                "company": q.company,
                "category": q.category,
                "question": q.question,
            }
            for q in questions
        ],
    }


@router.post("/{interview_id}/submit")
def submit_answer(
    interview_id: int, payload: AnswerSubmit, db: Session = Depends(get_db)
):
    """提交一道题的回答，评估并持久化，返回评分、点评与标准答案。"""
    interview = db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "面试会话不存在")
    if interview.status != "in_progress":
        raise HTTPException(400, "该面试已结束")

    item = db.get(KnowledgeItem, payload.knowledge_item_id)
    if not item:
        raise HTTPException(404, "题目不存在")

    result = evaluate_answer(
        company=item.company,
        question=item.question,
        standard_answer=item.standard_answer,
        scoring_points=item.scoring_points,
        user_answer=payload.answer,
        llm=resolve_config(db),
    )

    answer = Answer(
        interview_id=interview_id,
        knowledge_item_id=item.id,
        company=item.company,
        category=item.category,
        question=item.question,
        standard_answer=item.standard_answer,
        user_answer=payload.answer,
        score=result.score,
        strengths=json.dumps(result.strengths, ensure_ascii=False),
        weaknesses=json.dumps(result.weaknesses, ensure_ascii=False),
        tags=json.dumps(result.tags, ensure_ascii=False),
        suggestion=result.suggestion,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)

    out = result.to_dict()
    out.update(
        {
            "answer_id": answer.id,
            "standard_answer": item.standard_answer,
            "scoring_points": item.scoring_points,
        }
    )
    return out


@router.post("/{interview_id}/finish")
def finish_interview(interview_id: int, db: Session = Depends(get_db)):
    """结束面试会话，返回已答题数与平均分。"""
    interview = db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "面试会话不存在")
    interview.status = "completed"
    interview.ended_at = datetime.now()
    db.commit()

    scores = db.execute(
        select(Answer.score).where(Answer.interview_id == interview_id)
    ).scalars().all()
    scores = [s for s in scores if s is not None]
    avg = round(sum(scores) / len(scores), 1) if scores else 0.0
    return {"interview_id": interview_id, "answered": len(scores), "avg_score": avg}


@router.get("/history")
def list_history(db: Session = Depends(get_db)):
    """历史面试会话列表（个人主页使用）。

    用一次聚合查询统计每场的答题数与平均分，避免逐场查询 answers（N+1）。
    """
    rows = db.execute(
        select(
            Interview.id,
            Interview.created_at,
            Interview.ended_at,
            Interview.status,
            func.count(Answer.id).label("answered"),
            func.avg(Answer.score).label("avg_score"),
        )
        .outerjoin(Answer, Answer.interview_id == Interview.id)
        .group_by(Interview.id)
        .order_by(Interview.id.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": iv_id,
            "created_at": created_at,
            "ended_at": ended_at,
            "status": status,
            "answered": answered or 0,
            "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
        }
        for iv_id, created_at, ended_at, status, answered, avg_score in rows
    ]


@router.get("/{interview_id}/report")
def get_report(interview_id: int, db: Session = Depends(get_db)):
    """单次面试的整体分析报告（逐题结果 + 综合评语）。"""
    interview = db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "面试会话不存在")

    answers = db.execute(
        select(Answer).where(Answer.interview_id == interview_id).order_by(Answer.id)
    ).scalars().all()
    scores = [a.score for a in answers if a.score is not None]
    avg = round(sum(scores) / len(scores), 1) if scores else 0.0

    report = build_report(answers, avg, resolve_config(db))
    report["interview_id"] = interview_id
    report["created_at"] = interview.created_at
    return report

"""用户画像路由：画像总览（实时计算）、历史快照。"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProfileSnapshot
from app.services.profile import compute_profile, save_snapshot

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """实时计算画像（板块得分/薄弱项/学习建议）。

    纯查询接口，不写数据库；历史快照改为 POST /snapshots 显式保存。
    """
    return compute_profile(db)


@router.post("/snapshots")
def create_snapshot(db: Session = Depends(get_db)):
    """将当前画像保存为一条历史快照（仅保留最近 50 条）。"""
    content = compute_profile(db)
    snap = save_snapshot(db, content)
    return {"id": snap.id, "created_at": snap.created_at, "content": content}


@router.get("/snapshots")
def snapshots(db: Session = Depends(get_db)):
    """画像历史快照（倒序）。"""
    rows = db.execute(
        select(ProfileSnapshot).order_by(ProfileSnapshot.id.desc()).limit(20)
    ).scalars().all()
    out = []
    for s in rows:
        try:
            content = json.loads(s.content)
        except json.JSONDecodeError:
            content = {}
        out.append({"id": s.id, "created_at": s.created_at, "content": content})
    return out

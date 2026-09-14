"""知识库路由：Excel/CSV 批量导入、模板下载、单条录入、列表筛选、编辑、删除、聚合。"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KnowledgeItem
from app.services.knowledge_import import parse_upload

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    category: str
    question: str
    standard_answer: str
    scoring_points: str
    source_file: str
    created_at: datetime


class KnowledgePage(BaseModel):
    """分页结果：当前页数据 + 总数与分页信息。"""

    items: List[KnowledgeItemOut]
    total: int
    limit: int
    offset: int


class KnowledgeItemUpdate(BaseModel):
    company: str
    category: str
    question: str
    standard_answer: str
    scoring_points: str = ""


class KnowledgeItemCreate(BaseModel):
    company: str
    category: str
    question: str
    standard_answer: str
    scoring_points: str = ""


# 模板 CSV 内容（带 BOM 便于 Excel 打开不乱码；评分要点可选）
TEMPLATE_CSV = (
    "公司,类别,题目,标准答案,评分要点\n"
    "示例公司,Java基础,String 和 StringBuilder 的区别？,"
    "String 是不可变对象，每次修改都会产生新对象；StringBuilder 可变、适合频繁拼接、非线程安全。,"
    "说明不可变性;说明性能优势;提及线程安全(StringBuffer)\n"
)


def _to_out(item: KnowledgeItem) -> KnowledgeItemOut:
    return KnowledgeItemOut.model_validate(item)


def _import_items(db: Session, items, source_file: str) -> dict:
    """按公司+类别+题目去重后批量入库，返回导入统计。

    一次性取出库中已存在的键并在内存去重（同时处理同一文件内的重复），
    避免逐条 SELECT 造成的 N+1 查询。
    """
    if not items:
        return {"imported": 0, "skipped": 0, "total": 0}

    existing = {
        (row[0], row[1], row[2])
        for row in db.execute(
            select(
                KnowledgeItem.company,
                KnowledgeItem.category,
                KnowledgeItem.question,
            )
        ).all()
    }
    seen = set(existing)
    imported = 0
    skipped = 0
    for it in items:
        key = (it.company, it.category, it.question)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)  # 同一文件内的重复也只入库一条
        db.add(
            KnowledgeItem(
                company=it.company,
                category=it.category,
                question=it.question,
                standard_answer=it.standard_answer,
                scoring_points=it.scoring_points,
                source_file=source_file,
            )
        )
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "total": imported + skipped}


@router.get("/template")
def download_template():
    """下载题库模板（CSV），供用户按列填写后上传。"""
    return Response(
        TEMPLATE_CSV.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="knowledge_template.csv"'},
    )


@router.post("/upload")
async def upload(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """上传题库文件（仅 .csv / .xlsx），解析并批量导入。"""
    filename = file.filename or ""
    raw = await file.read()
    try:
        items = parse_upload(filename, raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    if not items:
        raise HTTPException(400, "文件中没有可导入的题目，请按模板填写公司/类别/题目/标准答案")
    return _import_items(db, items, filename)


@router.post("/items", response_model=KnowledgeItemOut)
def create_item(payload: KnowledgeItemCreate, db: Session = Depends(get_db)):
    """单条录入一道题目（按模板字段）。"""
    existing = db.execute(
        select(KnowledgeItem).where(
            KnowledgeItem.company == payload.company,
            KnowledgeItem.category == payload.category,
            KnowledgeItem.question == payload.question,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "该题目已存在")

    item = KnowledgeItem(
        company=payload.company,
        category=payload.category,
        question=payload.question,
        standard_answer=payload.standard_answer,
        scoring_points=payload.scoring_points,
        source_file="手动录入",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.get("/items", response_model=KnowledgePage)
def list_items(
    company: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="起始偏移"),
    db: Session = Depends(get_db),
):
    """分页返回题目列表（关键词匹配题目与标准答案）。

    返回 `{items, total, limit, offset}`，其中 total 为筛选后的总条数。
    """
    conds = []
    if company:
        conds.append(KnowledgeItem.company == company)
    if category:
        conds.append(KnowledgeItem.category == category)
    if keyword:
        conds.append(
            KnowledgeItem.question.contains(keyword)
            | KnowledgeItem.standard_answer.contains(keyword)
        )

    count_q = select(func.count(KnowledgeItem.id))
    items_q = select(KnowledgeItem)
    if conds:
        count_q = count_q.where(*conds)
        items_q = items_q.where(*conds)

    total = db.execute(count_q).scalar() or 0
    rows = db.execute(
        items_q.order_by(KnowledgeItem.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return KnowledgePage(
        items=[_to_out(it) for it in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/items/{item_id}", response_model=KnowledgeItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "题目不存在")
    return _to_out(item)


@router.put("/items/{item_id}", response_model=KnowledgeItemOut)
def update_item(
    item_id: int, payload: KnowledgeItemUpdate, db: Session = Depends(get_db)
):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "题目不存在")
    item.company = payload.company
    item.category = payload.category
    item.question = payload.question
    item.standard_answer = payload.standard_answer
    item.scoring_points = payload.scoring_points
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "题目不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    rows = db.execute(select(KnowledgeItem.company).distinct()).scalars().all()
    return sorted(r for r in rows if r)


@router.get("/categories")
def list_categories(
    company: Optional[str] = Query(None), db: Session = Depends(get_db)
):
    q = select(KnowledgeItem.category).distinct()
    if company:
        q = q.where(KnowledgeItem.company == company)
    rows = db.execute(q).scalars().all()
    return sorted(r for r in rows if r)

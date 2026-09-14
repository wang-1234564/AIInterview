"""抽题逻辑：按公司/类别/数量从知识库随机抽取题目。"""
import random
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeItem


def draw_questions(
    db: Session,
    company: Optional[str] = None,
    category: Optional[str] = None,
    count: int = 5,
) -> List[KnowledgeItem]:
    """随机抽取题目。

    - company/category 为空表示不限制该维度
    - 需求数量 >= 可抽数量时返回全部（打乱顺序）
    """
    q = select(KnowledgeItem)
    if company:
        q = q.where(KnowledgeItem.company == company)
    if category:
        q = q.where(KnowledgeItem.category == category)
    items = db.execute(q).scalars().all()
    if not items:
        return []
    if count <= 0:
        return []
    if count >= len(items):
        result = list(items)
        random.shuffle(result)
        return result
    return random.sample(list(items), count)

"""SQLite ORM 模型（单用户本地应用）。

字段说明：
- AppSetting      应用级设置（LLM 供应商 / api_key / base_url / model，单行）
- KnowledgeItem   题库条目（公司/类别/题目/标准答案/评分要点/来源文件）
- Interview       一次模拟面试会话
- Answer          面试中一道题的回答与评估结果
- ProfileSnapshot 用户画像快照（板块得分/薄弱项/学习建议）
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now()


class AppSetting(Base):
    """应用级设置，单行（id=1）：用户可在设置页选择 LLM 供应商并填写 Key。"""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), default="deepseek")
    api_key: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(200), index=True, default="")
    category: Mapped[str] = mapped_column(String(200), index=True, default="")
    question: Mapped[str] = mapped_column(Text)
    standard_answer: Mapped[str] = mapped_column(Text)
    scoring_points: Mapped[str] = mapped_column(Text, default="")  # 可选评分要点
    source_file: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    answers: Mapped[List["Answer"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id"), index=True
    )
    knowledge_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_items.id"), nullable=True
    )
    # 冗余存公司/类别，题目删除后画像仍可聚合
    company: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(200), default="")
    question: Mapped[str] = mapped_column(Text)
    standard_answer: Mapped[str] = mapped_column(Text, default="")
    user_answer: Mapped[str] = mapped_column(Text)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strengths: Mapped[str] = mapped_column(Text, default="[]")  # JSON array[str]
    weaknesses: Mapped[str] = mapped_column(Text, default="[]")  # JSON array[str]
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON array[str]
    suggestion: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    interview: Mapped["Interview"] = relationship(back_populates="answers")


class ProfileSnapshot(Base):
    __tablename__ = "profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    content: Mapped[str] = mapped_column(Text)  # JSON：板块得分/薄弱项/建议

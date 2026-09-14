"""面试整体分析报告生成：汇总单题结果，调用 LLM 生成综合评语（无 key 时规则兜底）。"""
import json
from typing import List

from app.models import Answer
from app.services.deepseek import DeepSeekClient, DeepSeekError
from app.services.llm_config import LLMConfig


def _json_list(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
        return [str(v) for v in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def build_report_messages(answers: List[Answer], avg_score: float) -> List[dict]:
    lines = [f"本场面试平均贴合度：{avg_score}，共 {len(answers)} 题。\n"]
    for i, a in enumerate(answers, 1):
        strengths = "、".join(_json_list(a.strengths)) or "无"
        weaknesses = "、".join(_json_list(a.weaknesses)) or "无"
        lines.append(
            f"{i}. 【{a.category}】{a.question}\n"
            f"   得分：{a.score}\n"
            f"   优点：{strengths}\n"
            f"   不足：{weaknesses}"
        )
    system = (
        "你是一位面试教练。请根据候选人在一场模拟面试中的逐题表现，"
        "用中文写一段 200 字左右的整体分析报告，包括：整体表现评价、"
        "共性优点、共性不足、以及下一步学习建议。直接输出报告正文，不要列标题。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(lines)},
    ]


def _mock_summary(answers: List[Answer], avg_score: float) -> str:
    if not answers:
        return "本场面试没有作答记录。"
    low = [a for a in answers if (a.score or 0) < 60]
    cats = {}
    for a in answers:
        cats[a.category] = cats.get(a.category, 0) + 1
    weakest = min(cats, key=cats.get) if cats else "未知板块"
    text = f"本场面试平均贴合度 {avg_score} 分，共作答 {len(answers)} 题。"
    if low:
        text += f"其中有 {len(low)} 题得分低于 60，建议重点复习相关知识点。"
    text += f"答题覆盖最少的板块是「{weakest}」，可针对性加强。"
    text += "（mock 模式）配置 DEEPSEEK_API_KEY 后可获得更细致的综合分析。"
    return text


SUMMARY_MAX_TOKENS = 1600


def generate_summary(
    answers: List[Answer], avg_score: float, llm: LLMConfig
) -> dict:
    """生成面试综合评语。

    返回 {text, source, warning}；降级时会带上 warning 供前端提示。
    """
    warning = ""
    if llm.enabled:
        client = DeepSeekClient(llm)
        try:
            text = client.chat(
                build_report_messages(answers, avg_score),
                temperature=0.5,
                max_tokens=SUMMARY_MAX_TOKENS,
            )
            if text.strip():
                return {"text": text.strip(), "source": "llm", "warning": ""}
            warning = "大模型未返回有效内容，本报告的综合评语由本地规则生成。"
        except DeepSeekError as exc:
            warning = f"大模型调用失败，本报告的综合评语由本地规则生成：{exc}"
    return {
        "text": _mock_summary(answers, avg_score),
        "source": "mock",
        "warning": warning,
    }


def build_report(answers: List[Answer], avg_score: float, llm: LLMConfig) -> dict:
    """组装单次面试的完整报告。"""
    items = [
        {
            "question": a.question,
            "category": a.category,
            "company": a.company,
            "score": a.score,
            "strengths": _json_list(a.strengths),
            "weaknesses": _json_list(a.weaknesses),
            "suggestion": a.suggestion,
            "user_answer": a.user_answer,
            "standard_answer": a.standard_answer,
        }
        for a in answers
    ]
    summary = generate_summary(answers, avg_score, llm)
    return {
        "avg_score": avg_score,
        "answered": len(answers),
        "summary": summary["text"],
        "summary_source": summary["source"],
        "summary_warning": summary["warning"],
        "items": items,
    }

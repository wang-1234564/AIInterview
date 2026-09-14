"""回答评估器：调用 DeepSeek 或 mock，返回结构化评估结果。

评估维度：贴合度(0-100)、优点、不足、板块标签、改进建议、总体评语。
无 API Key（或强制 mock）时使用 mock 启发式评估，保证流程可跑通。
"""
import json
import re
from dataclasses import asdict, dataclass, field
from typing import List

from app.services.deepseek import DeepSeekClient, DeepSeekError
from app.services.llm_config import LLMConfig


@dataclass
class Evaluation:
    score: float
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    suggestion: str = ""
    summary: str = ""
    # 结果来源：llm=真实大模型；mock=本地规则；mock_fallback=大模型调用/解析失败后降级
    source: str = "mock"
    warning: str = ""
    # 是否从大模型成功解析出结构化评分（mock 与降级结果均为 False）
    parsed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


SYSTEM_PROMPT = (
    "你是一位资深的面试官，负责评估候选人对面试题的回答。"
    "请严格以标准答案为基准，客观评估用户回答的贴合程度，指出优点与不足，并给出改进建议。"
    '你必须只输出一个 JSON 对象，不要输出任何其他文字、不要使用 Markdown 代码块。'
    'JSON 格式：{"score": 0到100的整数贴合度, "strengths": ["优点"], "weaknesses": ["不足"], '
    '"tags": ["相关知识点或板块标签"], "suggestion": "一句话改进建议", "summary": "一两句总体评语"}'
)


def build_eval_messages(
    company: str,
    question: str,
    standard_answer: str,
    scoring_points: str,
    user_answer: str,
) -> List[dict]:
    user = (
        f"【公司】{company}\n"
        f"【题目】{question}\n"
        f"【标准答案】{standard_answer}\n"
        f"【评分要点】{scoring_points or '无'}\n"
        f"【用户回答】{user_answer}\n\n请评估。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _fallback_evaluation(raw: str) -> Evaluation:
    """JSON 解析失败时的降级：把原始文本作为评语，贴合度置 0。"""
    return Evaluation(score=0.0, summary=raw[:500], parsed=False)


def parse_evaluation(text: str) -> Evaluation:
    """解析模型返回的 JSON；支持被代码块/多余文字包裹的情况，失败则降级。"""
    if not text:
        return Evaluation(score=0.0, parsed=False)
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取第一个 {...} 块
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return _fallback_evaluation(text)

    def _str_list(value) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str) and value.strip():
            return [value]
        return []

    try:
        score = float(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    return Evaluation(
        score=score,
        strengths=_str_list(data.get("strengths")),
        weaknesses=_str_list(data.get("weaknesses")),
        tags=_str_list(data.get("tags")),
        suggestion=str(data.get("suggestion") or ""),
        summary=str(data.get("summary") or ""),
        parsed=True,
    )


def _mock_evaluate(user_answer: str, standard_answer: str) -> Evaluation:
    """mock 评估：按回答长度 + 标准答案关键词覆盖做简单启发式打分。"""
    answer = (user_answer or "").strip()
    if not answer:
        return Evaluation(
            score=0.0,
            strengths=[],
            weaknesses=["未作答"],
            tags=[],
            suggestion="请尝试用自己的话作答",
            summary="本题未作答",
        )
    # 关键词覆盖：取标准答案中的中文/英文词（长度>=2），统计命中率
    tokens = set(re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", standard_answer))
    hits = sum(1 for t in tokens if t in answer)
    coverage = (hits / len(tokens)) if tokens else 0.3
    length_bonus = min(len(answer) // 100 * 5, 20)
    score = round(min(95.0, 30 + coverage * 50 + length_bonus), 1)
    return Evaluation(
        score=score,
        strengths=["对题目作出了回答"] if answer else [],
        weaknesses=["未覆盖标准答案的全部要点"] if coverage < 0.6 else [],
        tags=["mock"],
        suggestion="（mock 模式）配置 DEEPSEEK_API_KEY 后可获得真实评估",
        summary=f"mock 评估：关键词覆盖 {coverage:.0%}，长度加分 {length_bonus}",
    )


EVAL_MAX_TOKENS = 4096  # reasoning 模型会额外消耗 token，预留足够预算避免返回被截断


def _degraded(user_answer: str, standard_answer: str, warning: str) -> Evaluation:
    """真实评估失败后的降级结果（明确标注来源与原因）。"""
    ev = _mock_evaluate(user_answer, standard_answer)
    ev.source = "mock_fallback"
    ev.warning = warning
    return ev


def evaluate_answer(
    company: str,
    question: str,
    standard_answer: str,
    scoring_points: str,
    user_answer: str,
    llm: LLMConfig,
) -> Evaluation:
    """评估单个回答：配置了可用的大模型时调用，否则 mock。

    大模型调用失败或返回无法解析时，会明确标注 source / warning，
    不再把降级结果当作真实评估静默返回。
    """
    if llm.enabled:
        client = DeepSeekClient(llm)
        try:
            text = client.chat(
                build_eval_messages(
                    company, question, standard_answer, scoring_points, user_answer
                ),
                json_mode=True,
                max_tokens=EVAL_MAX_TOKENS,
            )
            ev = parse_evaluation(text)
            if ev.parsed and text.strip():
                ev.source = "llm"
                return ev
            return _degraded(
                user_answer,
                standard_answer,
                "大模型返回的内容无法解析为评分（可能被推理内容占满 token），"
                "本次结果由本地规则给出。",
            )
        except DeepSeekError as exc:
            return _degraded(
                user_answer,
                standard_answer,
                f"大模型调用失败，本次结果由本地规则给出：{exc}",
            )
    ev = _mock_evaluate(user_answer, standard_answer)
    ev.source = "mock"
    return ev

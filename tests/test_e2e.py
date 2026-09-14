"""端到端回归测试：导入题库 → 列表 → 模拟面试 → 报告 → 画像。"""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_knowledge.csv"


def test_end_to_end_flow(db):
    with TestClient(app) as client:
        # 1. 导入 CSV 题库
        with open(SAMPLE, "rb") as f:
            r = client.post(
                "/api/knowledge/upload",
                files={"file": ("sample.csv", f, "text/csv")},
            )
        assert r.status_code == 200
        assert r.json()["imported"] == 4

        # 2. 题库列表（分页结构）
        page = client.get("/api/knowledge/items").json()
        assert page["total"] == 4
        assert len(page["items"]) == 4

        # 3. 创建面试（抽 3 题）
        r = client.post("/api/interview/create", json={"count": 3})
        assert r.status_code == 200
        interview_id = r.json()["interview_id"]
        questions = r.json()["questions"]
        assert len(questions) == 3

        # 4. 逐题提交回答（mock 评估）
        for q in questions:
            s = client.post(
                f"/api/interview/{interview_id}/submit",
                json={"knowledge_item_id": q["id"], "answer": "这是我的回答内容"},
            )
            assert s.status_code == 200
            assert "score" in s.json()
            assert "standard_answer" in s.json()

        # 5. 结束面试
        f = client.post(f"/api/interview/{interview_id}/finish")
        assert f.status_code == 200
        assert f.json()["answered"] == 3

        # 6. 单次报告
        rep = client.get(f"/api/interview/{interview_id}/report").json()
        assert rep["answered"] == 3
        assert len(rep["items"]) == 3
        assert rep["summary"]

        # 7. 画像总览
        ov = client.get("/api/profile/overview").json()
        assert ov["stats"]["answered"] == 3
        assert ov["stats"]["interviews"] >= 1
        assert len(ov["categories"]) >= 1
        assert ov["advice"]

        # 8. 历史面试
        hist = client.get("/api/interview/history").json()
        assert any(h["id"] == interview_id for h in hist)

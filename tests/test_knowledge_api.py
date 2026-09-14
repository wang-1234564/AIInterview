"""知识库接口测试：导入去重与分页。"""
from fastapi.testclient import TestClient

from app.main import app


def _csv(*rows: str) -> bytes:
    return ("公司,类别,题目,标准答案\n" + "\n".join(rows)).encode("utf-8")


def test_upload_dedupes_within_file_and_across(db):
    """同一文件内的重复行、以及与库中已有记录重复，都应被跳过。"""
    payload = _csv(
        "A,Java,q1,a1",
        "A,Java,q1,a1",  # 文件内重复
        "A,Java,q2,a2",
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/knowledge/upload", files={"file": ("k.csv", payload, "text/csv")}
        )
        assert r.status_code == 200
        assert r.json() == {"imported": 2, "skipped": 1, "total": 3}

        # 再上传同一文件：全部跳过
        r2 = client.post(
            "/api/knowledge/upload", files={"file": ("k.csv", payload, "text/csv")}
        )
        assert r2.json() == {"imported": 0, "skipped": 3, "total": 3}


def test_items_pagination(db):
    with TestClient(app) as client:
        for i in range(25):
            client.post(
                "/api/knowledge/items",
                json={
                    "company": "C",
                    "category": "cat",
                    "question": f"q{i}",
                    "standard_answer": "a",
                },
            )

        p1 = client.get("/api/knowledge/items?limit=10&offset=0").json()
        assert p1["total"] == 25
        assert len(p1["items"]) == 10
        assert p1["limit"] == 10 and p1["offset"] == 0

        p3 = client.get("/api/knowledge/items?limit=10&offset=20").json()
        assert len(p3["items"]) == 5

        # 默认每页 20 条
        default = client.get("/api/knowledge/items").json()
        assert default["limit"] == 20

        # 越界参数被拒绝
        assert client.get("/api/knowledge/items?limit=0").status_code == 422
        assert client.get("/api/knowledge/items?limit=999").status_code == 422
        assert client.get("/api/knowledge/items?offset=-1").status_code == 422

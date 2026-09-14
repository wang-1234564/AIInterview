from app.models import KnowledgeItem
from app.services.draw import draw_questions


def test_draw_questions(db):
    for i in range(8):
        db.add(KnowledgeItem(company="A", category="java", question=f"q{i}", standard_answer="a"))
    for i in range(3):
        db.add(KnowledgeItem(company="B", category="algo", question=f"b{i}", standard_answer="a"))
    db.commit()

    assert len(draw_questions(db, count=5)) == 5
    assert len(draw_questions(db, company="B")) == 3
    assert len(draw_questions(db, category="java", count=2)) == 2
    assert draw_questions(db, company="X") == []
    assert len(draw_questions(db, count=100)) == 11  # 超量返回全部
    assert draw_questions(db, count=0) == []

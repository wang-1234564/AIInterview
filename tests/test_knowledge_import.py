import io

from openpyxl import Workbook

from app.services.knowledge_import import parse_csv, parse_excel, parse_upload


def test_parse_csv_basic():
    content = "公司,类别,题目,标准答案,评分要点\nA,Java,q1,a1,p1\n"
    items = parse_csv(content.encode("utf-8"))
    assert len(items) == 1
    it = items[0]
    assert it.company == "A"
    assert it.category == "Java"
    assert it.question == "q1"
    assert it.standard_answer == "a1"
    assert it.scoring_points == "p1"


def test_parse_csv_english_headers():
    content = "company,category,question,standard_answer,scoring_points\nB,Algo,q2,a2,p2\n"
    items = parse_csv(content.encode("utf-8"))
    assert len(items) == 1
    assert items[0].company == "B"


def test_parse_csv_gbk_encoding():
    content = "公司,类别,题目,标准答案\nA,Java,问题,答案\n"
    items = parse_csv(content.encode("gbk"))
    assert len(items) == 1
    assert items[0].question == "问题"


def test_parse_csv_skips_incomplete_rows():
    content = "公司,类别,题目,标准答案\nA,Java,q1,a1\nX,Y,,\n"
    items = parse_csv(content.encode("utf-8"))
    assert len(items) == 1


def test_parse_excel():
    wb = Workbook()
    ws = wb.active
    ws.append(["公司", "类别", "题目", "标准答案", "评分要点"])
    ws.append(["C", "Net", "q3", "a3", "p3"])
    buf = io.BytesIO()
    wb.save(buf)
    items = parse_excel(buf.getvalue())
    assert len(items) == 1
    assert items[0].question == "q3"
    assert items[0].scoring_points == "p3"


def test_missing_required_column():
    content = "公司,题目,标准答案\nA,q1,a1\n"  # 缺「类别」列
    try:
        parse_csv(content.encode("utf-8"))
        assert False, "should raise"
    except ValueError as exc:
        assert "category" in str(exc)


def test_parse_upload_rejects_other_types():
    try:
        parse_upload("a.md", b"# x")
        assert False, "should raise"
    except ValueError as exc:
        assert "仅支持" in str(exc)


def test_alias_columns():
    content = "公司,分类,问题,答案,考点\nA,Cat,qx,ax,kx\n"
    items = parse_csv(content.encode("utf-8"))
    assert len(items) == 1
    assert items[0].category == "Cat"
    assert items[0].question == "qx"
    assert items[0].standard_answer == "ax"
    assert items[0].scoring_points == "kx"

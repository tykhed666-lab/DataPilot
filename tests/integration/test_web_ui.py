from fastapi.testclient import TestClient

from datapilot.api.app import create_app


def test_root_serves_dependency_free_workbench_and_assets() -> None:
    with TestClient(create_app()) as client:
        page = client.get("/")
        stylesheet = client.get("/static/app.css")
        script = client.get("/static/app.js")
        docs = client.get("/docs")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "DataPilot 分析工作台" in page.text
    assert 'id="dataset-file"' in page.text
    assert 'id="question"' in page.text
    assert 'id="approve-button"' in page.text
    assert 'id="report-output"' in page.text
    assert 'src="/static/app.js"' in page.text
    assert 'href="/static/app.css"' in page.text
    assert "OPENAI_API_KEY" not in page.text

    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "localStorage" in script.text
    assert "textContent" in script.text
    assert docs.status_code == 200

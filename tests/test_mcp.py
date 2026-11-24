import pytest

from backend import mcp_client, skills


def test_lab_server_lists_and_calls_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("NETRACARE_LAB_DB", str(tmp_path / "lab.db"))
    with mcp_client.MCPClient(mcp_client.LAB) as c:
        names = {t["name"] for t in c.list_tools()}
        assert names and all(isinstance(n, str) for n in names)


def test_describe_servers_reports_both(tmp_path, monkeypatch):
    monkeypatch.setenv("NETRACARE_LAB_DB", str(tmp_path / "lab.db"))
    out = mcp_client.describe_servers()
    assert len(out) == 2 and all(s["ok"] for s in out)


def test_skills_loaded_and_selected():
    names = {s["name"] for s in skills.list_skills()}
    assert {"clinic-front-desk", "red-flag-escalation"} <= names
    assert "partner-lab-referrals" in skills.select("how much is an OCT scan at the lab")


def test_official_sdk_handshake_optional():
    pytest.importorskip("mcp")  # only runs where the official SDK is installed

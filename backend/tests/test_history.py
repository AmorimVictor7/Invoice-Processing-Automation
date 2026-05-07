async def test_list_history_empty(client):
    r = await client.get("/api/history/")
    assert r.status_code == 200
    data = r.json()
    assert data["entries"] == []
    assert data["total"] == 0


async def test_delete_all_empty(client):
    r = await client.delete("/api/history/all")
    assert r.status_code == 200
    assert r.json()["deleted"] == 0


async def test_delete_entry_not_found(client):
    r = await client.delete("/api/history/nonexistent-id")
    assert r.status_code == 404

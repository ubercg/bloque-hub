"""Subida de imágenes promo de espacios y servido público /api/media/space-promo/..."""

MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'\x00\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


def test_upload_promo_media_superadmin_and_public_get(
    client, token_superadmin_a, tenant_b
):
    from app.core.config import settings

    r = client.post(
        f"/api/spaces/promo-media/upload?tenant_id={tenant_b.id}",
        files={"file": ("one.png", MIN_PNG, "image/png")},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.startswith("/api/media/space-promo/")
    assert str(tenant_b.id) in url

    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.content == MIN_PNG
    assert "image" in (r2.headers.get("content-type") or "")

    # Limpieza (evitar acumulación en data/ de tests)
    from pathlib import Path

    name = url.rsplit("/", 1)[-1]
    p = Path(settings.SPACE_PROMO_MEDIA_PATH) / str(tenant_b.id) / name
    if p.is_file():
        p.unlink()


def test_upload_promo_media_rejects_non_image(client, token_superadmin_a, tenant_b):
    r = client.post(
        f"/api/spaces/promo-media/upload?tenant_id={tenant_b.id}",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 400


def test_public_media_invalid_filename_404(client):
    import uuid

    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    r = client.get(f"/api/media/space-promo/{tid}/not-valid-hex-name.png")
    assert r.status_code == 404

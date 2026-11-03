"""Files the render server can't read, made into ones it can as they come in: a PDF kept as its words, an iPhone's HEIC
photo and an AVIF made a JPEG (a PNG when they have transparency)."""

import io

from PIL import Image

from test_api import register
from test_uploads import upload


def pdf(text):
    """A one-page PDF with `text` on it, written by hand: the smallest one a reader takes."""
    stream = "BT /F1 18 Tf 40 700 Td ({}) Tj ET".format(text).encode("latin-1")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, places = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for n, body in enumerate(objects, start=1):
        places.append(out.tell())
        out.write(b"%d 0 obj\n" % n + body + b"\nendobj\n")
    start = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % p for p in places))
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, start))
    return out.getvalue()


def picture(fmt, mode="RGB"):
    import pillow_heif
    pillow_heif.register_heif_opener()
    out = io.BytesIO()
    Image.new(mode, (64, 48), (200, 40, 40, 128) if mode == "RGBA" else (200, 40, 40)).save(out, fmt)
    return out.getvalue()


def test_a_pdf_is_kept_as_its_words(client):
    me = register(client)
    made = upload(client, "Ep 121 script.pdf", pdf("Violet stared at the crisp stack of bills.")).json()
    assert made["kind"] == "text" and made["filename"].endswith(".txt")
    folder = client.app.state.outputs.folder(me["id"])
    assert "Violet stared at the crisp stack of bills." in (folder / made["filename"]).read_text(encoding="utf-8")
    refused = upload(client, "fake.pdf", b"%PDF-1.4 nothing here")
    assert refused.status_code == 400 and "fake.pdf could not be read" in refused.json()["detail"]


def test_heic_and_avif_photos_come_in_as_pictures_every_workflow_reads(client):
    me = register(client)
    folder = client.app.state.outputs.folder(me["id"])
    heic = upload(client, "IMG_0042.HEIC", picture("HEIF")).json()
    assert heic["kind"] == "image" and heic["filename"].endswith(".jpg")
    assert Image.open(folder / heic["filename"]).size == (64, 48)
    avif = upload(client, "sticker.avif", picture("AVIF", "RGBA")).json()
    assert avif["kind"] == "image" and avif["filename"].endswith(".png")   # its transparency is kept
    assert upload(client, "not-a-photo.heic", b"\x00" * 64).status_code == 400

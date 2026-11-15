"""Write small, valid PDFs for tests (standard library only)."""
import zlib


def make_pdf(pages, title=None, compress=True):
    """pages: list of lists of text lines. Returns PDF bytes with an xref table."""
    objects = []

    def add(body):
        objects.append(body)
        return len(objects)

    font = add(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    page_ids, content_ids = [], []
    pages_id = len(objects) + 2 * len(pages) + 1
    for i, lines in enumerate(pages):
        ops = [b'BT', b'/F1 12 Tf', b'72 720 Td']
        for line in lines:
            escaped = line.encode('latin-1').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
            ops += [b'(' + escaped + b') Tj', b'0 -16 Td']
        ops.append(b'ET')
        data = b'\n'.join(ops)
        if compress and i % 2:
            data = zlib.compress(data)
            content = add(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(data) + data + b'\nendstream')
        else:
            content = add(b'<< /Length %d >>\nstream\n' % len(data) + data + b'\nendstream')
        page = add(b'<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R '
                   b'/Resources << /Font << /F1 %d 0 R >> >> >>' % (pages_id, content, font))
        page_ids.append(page)
    assert add(b'<< /Type /Pages /Kids [' + b' '.join(b'%d 0 R' % x for x in page_ids) + b'] /Count %d >>' % len(page_ids)) == pages_id
    catalog = add(b'<< /Type /Catalog /Pages %d 0 R >>' % pages_id)
    info = add(b'<< /Title (' + title.encode('latin-1') + b') >>') if title else None
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % number + body + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    out += b''.join(b'%010d 00000 n \n' % x for x in offsets)
    out += b'trailer\n<< /Size %d /Root %d 0 R' % (len(objects) + 1, catalog)
    out += (b' /Info %d 0 R' % info if info else b'') + b' >>\nstartxref\n%d\n%%%%EOF\n' % xref
    return bytes(out)

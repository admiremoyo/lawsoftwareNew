from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa


class PDFError(Exception):
    pass


def render_pdf(template, context):
    html = render_to_string(template, context)
    out = BytesIO()
    result = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if result.err:
        raise PDFError(f"Could not render {template}")
    return out.getvalue()


def pdf_response(template, context, filename, inline=True):
    response = HttpResponse(render_pdf(template, context), content_type="application/pdf")
    disposition = "inline" if inline else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response

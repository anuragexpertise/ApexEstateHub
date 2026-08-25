# app/dash_apps/callbacks/print_letterhead.py
"""
Shared letterhead for every printed/emailed document (receipts, NOCs, event
tickets, and any future print flow).

Why this exists
----------------
Before this module, receipt_callbacks.py and noc_callbacks.py each built
their own plain-text/plain-HTML print window with no society branding at
all — no logo, no background, no signature, no verification QR. Rather
than duplicate that branding markup three times (receipt / NOC / event
ticket), the header/watermark/footer layout lives here once, and each
print flow only supplies its own body HTML + a small `assets` dict.

Two halves:
  - get_letterhead_assets(society, society_id) — Python side, resolves the
    society's logo / login_background / secretary_sign columns to actual
    URLs via renderers.get_image_url, so callers don't need to know the
    /assets/<society_id>/<file> URL convention themselves.
  - LETTERHEAD_JS — a JS snippet defining buildLetterheadDoc(opts), which
    each clientside print/PDF/email callback concatenates onto its own JS
    function string (same pattern already used for _receipt_html_js()).

Design choices carried over from the clarifying-questions round:
  - Print background reuses societies.login_background (no new column) —
    rendered as a faint (6% opacity) full-page watermark, not a loud image,
    so it doesn't fight with the printed text.
  - Signature reuses societies.secretary_sign (no separate admin_signature
    column).
"""

QR_CAPTION = "Scan to verify this document"


def get_letterhead_assets(society: dict, society_id) -> dict:
    """
    Resolve a society's branding columns to URLs the print window's <img>
    tags can load directly. Returns empty strings (not None) for missing
    assets so JS string-concatenation callers don't need null checks.
    """
    from app.dash_apps.drilldown.renderers import get_image_url

    society = society or {}
    return {
        "society_name": society.get("name") or "",
        "society_address": society.get("address") or "",
        "secretary_name": society.get("secretary_name") or "Authorised Signatory",
        "logo_url": get_image_url(society.get("logo"), None, "society", society_id) or "",
        "background_url": get_image_url(society.get("login_background"), None, "society", society_id) or "",
        "signature_url": get_image_url(society.get("secretary_sign"), None, "society", society_id) or "",
    }


# ── JS: buildLetterheadDoc(opts) ────────────────────────────────────────
# opts: { title, societyName, societyAddress, logoUrl, backgroundUrl,
#         bodyHtml, signatureUrl, secretaryName, qrUrl, qrCaption,
#         printWidth }
# All fields optional except bodyHtml — the header/footer sections quietly
# collapse to nothing when their asset URL is empty, so a society with no
# logo/signature/QR yet still gets a clean printout, not broken <img> tags.
LETTERHEAD_JS = r"""
function buildLetterheadDoc(o) {
    var bg = o.backgroundUrl
        ? '<div style="position:fixed;inset:0;background-image:url(' + o.backgroundUrl + ');' +
          'background-size:cover;background-position:center;opacity:0.2;z-index:-1"></div>'
        : '';

    var logo = o.logoUrl
        ? '<img src="' + o.logoUrl + '" style="height:56px;max-width:160px;object-fit:contain;margin-bottom:8px" />'
        : '';

    var header = (
        '<div style="text-align:center;margin-bottom:20px;padding-bottom:14px;border-bottom:2px solid #15304f22">' +
        logo +
        '<div style="font-weight:800;font-size:18px;color:#15304f">' + (o.societyName || '') + '</div>' +
        (o.societyAddress ? '<div style="font-size:11px;color:#777;margin-top:2px">' + o.societyAddress + '</div>' : '') +
        '</div>'
    );

    var sigBlock = o.signatureUrl
        ? '<img src="' + o.signatureUrl + '" style="height:46px;object-fit:contain;display:block;margin-bottom:4px" />'
        : '<div style="height:46px"></div>';

    var qrBlock = o.qrUrl
        ? ('<div style="text-align:center">' +
           '<img src="' + o.qrUrl + '" style="width:76px;height:76px;border:1px solid #ddd;border-radius:6px" />' +
           '<div style="font-size:9px;color:#999;margin-top:4px;max-width:90px">' + (o.qrCaption || 'Scan to verify') + '</div>' +
           '</div>')
        : '';

    var footer = (
        '<div style="display:flex;justify-content:space-between;align-items:flex-end;' +
        'margin-top:40px;padding-top:14px;border-top:1px dashed #ccc">' +
        '<div style="text-align:center;min-width:170px">' +
        sigBlock +
        '<div style="font-size:11px;font-weight:600;border-top:1px solid #999;padding-top:4px;margin-top:2px">' +
        (o.secretaryName || 'Authorised Signatory') + '</div>' +
        '<div style="font-size:9px;color:#999">Authorised Signatory</div>' +
        '</div>' +
        qrBlock +
        '</div>'
    );

    return (
        '<html><head><title>' + (o.title || 'Document') + '</title>' +
        '<style>' +
        '@page{size:A4;margin:10mm}' +
        'html,body{margin:0}' +
        'body{font-family:Arial,sans-serif;padding:24px;max-width:' + (o.printWidth || '650px') +
        ';margin:auto;position:relative}' +
        '@media print{body{padding:8px 4px}img{max-width:100%}}' +
        '</style>' +
        '</head><body>' +
        bg + header + (o.bodyHtml || '') + footer +
        '</body></html>'
    );
}

function buildLetterheadPdfDoc(o) {
    var doc = buildLetterheadDoc(o);
    var bodyMatch = doc.match(/<body[^>]*>([\s\S]*)<\/body>/i);
    var bodyContent = bodyMatch ? bodyMatch[1] : doc;
    var title = o.title || 'Document';
    var filename = (o.filename || title).replace(/[^a-z0-9_.-]/gi, '_') + '.pdf';

    return (
        '<!DOCTYPE html><html><head><title>' + title + '</title>' +
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"><\/script>' +
        '<style>@page{size:A4;margin:10mm}body{margin:0;font-family:Arial,sans-serif}</style>' +
        '</head><body onload="generatePdf()">' +
        bodyContent +
        '<script>' +
        'function generatePdf(){' +
        '  var imgs=document.images,pending=imgs.length,loaded=0;' +
        '  function doPdf(){' +
        '    try{' +
        '      html2pdf().from(document.body).set({' +
        '        margin:10,filename:"' + filename + '",' +
        '        image:{type:"jpeg",quality:0.98},' +
        '        html2canvas:{scale:2,useCORS:true,backgroundColor:"#ffffff"},' +
        '        jsPDF:{unit:"mm",format:"a4",orientation:"portrait"}' +
        '      }).save();' +
        '    }catch(e){console.error("PDF generation failed:",e);}' +
        '  }' +
        '  if(!pending){doPdf();return;}' +
        '  for(var i=0;i<pending;i++){' +
        '    if(imgs[i].complete){loaded++;if(loaded===pending)doPdf();}' +
        '    else{imgs[i].onload=imgs[i].onerror=function(){loaded++;if(loaded===pending)doPdf();};}' +
        '  }' +
        '}' +
        '<\/script></body></html>'
    );
}
"""


def clientside_iife(js: str, fn_name: str) -> str:
    """
    Wrap a clientside callback's JS source in an IIFE that returns the real
    handler function.

    Dash injects the inline JS by literally doing
        ns["<hash>"] = <clientside_function>;
    If <clientside_function> is several `function foo(){}` declarations (the
    common "helpers + main function" pattern used by the print/PDF callbacks
    here), only the FIRST declaration is assigned to ns["<hash>"] — so the
    main handler is silently never called and the button does nothing. Wrapping
    everything in `(function(){ ...; return <fn_name>; })()` makes the whole
    thing a single expression that evaluates to the intended handler, fixing
    every print/PDF flow at once.
    """
    return "(function(){\n" + js + "\nreturn " + fn_name + ";\n})();"

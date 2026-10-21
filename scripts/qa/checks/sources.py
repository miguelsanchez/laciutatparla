"""Source checks (§7): is what we downloaded a real plenary acta?"""

from __future__ import annotations

import re
import shutil
import subprocess

from qa.model import Context, Finding, check

S7_MIN_CHARS = 2000  # the shortest real actas (one-item extraordinary sessions) are ~2.4k
S7_WRONG_DOC = re.compile(
    r"^\W*(ORDRE DEL DIA|ORDEN DEL D[IÍ]A)|JUNTA DE GOVERN LOCAL|JUNTA DE GOBIERNO LOCAL|JUNTA MUNICIPAL"
)
S7_ACTA = re.compile(r"\bACTA\b|\bSESSI[OÓ]|\bSESI[OÓ]N\b")


def _pages(pdf, cache: dict) -> int | None:
    """Page count via pdfinfo, cached by size+mtime in ctx.memory (pdfinfo costs ~25 ms each)."""
    st = pdf.stat()
    stamp = f"{st.st_size}:{int(st.st_mtime)}"
    hit = cache.get(pdf.name)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
    pages = int(m.group(1)) if r.returncode == 0 and m else 0
    cache[pdf.name] = [stamp, pages]
    return pages


@check("S7", family="sources", title="PDF is valid and is a plenary acta (not junta de govern / ordre del dia)")
def s7_is_plenary_acta(ctx: Context):
    have_pdfinfo = shutil.which("pdfinfo") is not None
    cache = ctx.memory.setdefault("s7_pdfinfo", {})
    for pdf in sorted(ctx.pdfs_dir.glob("*.pdf")):
        pleno_id = pdf.stem
        with open(pdf, "rb") as fh:
            magic = fh.read(5)
        if magic != b"%PDF-":
            yield Finding(check="S7", severity="P0", subject=pleno_id, key="magic",
                          message=f"not a PDF (starts with {magic!r})")
            continue
        if have_pdfinfo and _pages(pdf, cache) == 0:
            yield Finding(check="S7", severity="P0", subject=pleno_id, key="pages",
                          message="pdfinfo cannot read it (0 pages or corrupt)")
        text = ctx.text(pleno_id)
        if text is None:
            continue  # PDF without text is S2
        head = re.sub(r"\s+", " ", text[:3000]).upper()
        wrong = S7_WRONG_DOC.search(head[:600])
        if wrong:
            yield Finding(check="S7", severity="P0", subject=pleno_id, key="wrong-doc",
                          message=f"looks like another document, not a plenary acta: {wrong.group(0).strip()!r}",
                          details={"head": head[:200]})
        elif not S7_ACTA.search(head):
            yield Finding(check="S7", severity="P0", subject=pleno_id, key="no-acta-header",
                          message="no ACTA / SESSIÓ / SESIÓN in the first 3000 characters",
                          details={"head": head[:200]})
        if len(text) < S7_MIN_CHARS:
            yield Finding(check="S7", severity="P1", subject=pleno_id, key="short",
                          message=f"text has only {len(text)} characters (< {S7_MIN_CHARS})")


# ── S1: new sessions and newly published actas on valencia.es ────────────────

S1_PENDING_DAYS = 400  # look for a late acta for sessions up to this old


def _quiet(fn, *args, **kwargs):
    """The pipeline crawlers print progress; keep run_checks output clean."""
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


@check("S1", family="sources", title="new sessions / newly published actas on valencia.es; index shrinking",
       network=True)
def s1_new_sessions(ctx: Context):
    from datetime import date, timedelta

    from qa.checks.extraction import _check_new_sessions
    from qa.model import load_script

    crawler = _check_new_sessions()
    sessions_mod = load_script("02_crawl_sessions.py")
    index = {s["id"]: s for s in ctx.sessions_index}

    # The index must never lose sessions (01_crawl_index.py rewrites it whole, D12).
    prev = ctx.memory.get("s1_index_size")
    if prev is not None and len(index) < prev:
        yield Finding(check="S1", severity="P0", subject="sessions_index", key=f"{prev}->{len(index)}",
                      message=f"sessions_index.json shrank from {prev} to {len(index)} sessions")
    ctx.memory["s1_index_size"] = max(len(index), prev or 0)

    live = _quiet(crawler.crawl_recent_sessions, years_back=1)
    if not live:
        yield Finding(check="S1", severity="P0", subject="valencia.es", key="empty",
                      message="the session list on valencia.es returned 0 sessions "
                              "(site down or its structure changed)")
        return

    for sid, s in sorted(live.items()):
        if sid not in index:
            yield Finding(check="S1", severity="P1", subject=sid, key="new-session",
                          message=f"new session on valencia.es, not in sessions_index ({s['tipo']})",
                          details={"url": s["url_web"]})

    # Sessions without a local acta: has it been published since?
    meta = {m["id"]: m for m in ctx.sessions_metadata}
    cutoff = (date.today() - timedelta(days=S1_PENDING_DAYS)).isoformat()
    pending = sorted(
        sid for sid in set(index) | set(live)
        if not (ctx.pdfs_dir / f"{sid}.pdf").exists() and sid[:10] >= cutoff
    )
    for sid in pending:
        url = (meta.get(sid) or index.get(sid) or live.get(sid) or {}).get("url_web")
        if not url:
            continue
        try:
            soup = _quiet(crawler.fetch_html, url)
            acta = sessions_mod.extract_pdf_urls(soup, sid)["url_acta"]
        except Exception as e:  # noqa: BLE001
            yield Finding(check="S1", severity="P2", subject=sid, key="fetch-error",
                          message=f"could not read the session page: {type(e).__name__}")
            continue
        if acta:
            yield Finding(check="S1", severity="P1", subject=sid, key="acta-published",
                          message="acta published on valencia.es and not ingested yet: run /update-plenos",
                          details={"url_acta": acta, "url_web": url})
        else:
            yield Finding(check="S1", severity="P3", subject=sid, key="acta-pending",
                          message="session held, acta not published yet", details={"url_web": url})


# ── S2: pipeline gaps ────────────────────────────────────────────────────────

@check("S2", family="sources", title="acta published but no PDF, or PDF without text", fast=True)
def s2_pipeline_gaps(ctx: Context):
    """Gaps the pipeline should have filled. Sessions whose acta is not out yet are S1's
    (acta-pending); a header with 0 interventions is E9's."""
    if not ctx.pdfs_dir.is_dir():
        # A checkout without PDFs at all (the QA worktree made with `propose.py --sparse`)
        # cannot tell a missing download from a file it chose not to check out.
        return
    meta = {m["id"]: m for m in ctx.sessions_metadata}
    for s in ctx.sessions_index:
        sid = s["id"]
        if (meta.get(sid) or {}).get("acta_disponible") and not (ctx.pdfs_dir / f"{sid}.pdf").exists():
            yield Finding(check="S2", severity="P1", subject=sid, key="no-pdf",
                          message="acta marked as available in sessions_metadata but no PDF downloaded "
                                  "(run 03_download_pdfs.py)",
                          details={"url_acta": meta[sid].get("url_acta")})
    for pdf in sorted(ctx.pdfs_dir.glob("*.pdf")):
        if not (ctx.texts_dir / f"{pdf.stem}.txt").exists():
            yield Finding(check="S2", severity="P1", subject=pdf.stem, key="no-text",
                          message="PDF without extracted text (run 04_extract_text.py)")

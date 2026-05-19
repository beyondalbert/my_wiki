"""AI Knowledge Base blueprint (Karpathy LLM Wiki style)."""
import json
import os
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import (
    AIKnowledgeBase, AIKBSource, AIKBSourceKind, AIKBSourceStatus, AIKBStatus,
    AIKBArticle, AIKBLink, KnowledgeBase, Document,
)
from ..services import ai_service, kb_service
from ..utils.markdown import render_wiki_markdown
from ..utils.extract_upload import is_supported, ALL_SUPPORTED_EXTS

bp = Blueprint("ai", __name__)


def _get_ai_kb_or_404(ai_kb_id: str) -> AIKnowledgeBase:
    ai_kb = db.session.get(AIKnowledgeBase, ai_kb_id)
    if ai_kb is None:
        abort(404)
    if ai_kb.owner_id != current_user.id and not getattr(current_user, "is_super_admin", False):
        abort(403)
    return ai_kb


@bp.route("/")
@login_required
def index():
    items = AIKnowledgeBase.query.filter_by(owner_id=current_user.id).order_by(AIKnowledgeBase.updated_at.desc()).all()
    return render_template("ai/index.html", items=items)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_ai_kb():
    if request.method == "GET":
        return render_template("ai/new.html")
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not name:
        flash("请输入名称", "error")
        return redirect(url_for("ai.new_ai_kb"))
    ai_kb = AIKnowledgeBase(
        owner_id=current_user.id,
        name=name,
        description=description,
        chat_model=(request.form.get("chat_model") or "").strip(),
        enable_rag=False,
    )
    db.session.add(ai_kb)
    db.session.commit()
    flash("AI 知识库已创建", "success")
    return redirect(url_for("ai.detail", ai_kb_id=ai_kb.id))


@bp.route("/<ai_kb_id>")
@login_required
def detail(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    sources = AIKBSource.query.filter_by(ai_kb_id=ai_kb.id).all()
    articles = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).order_by(AIKBArticle.title.asc()).all()
    redlinks = AIKBLink.query.filter_by(ai_kb_id=ai_kb.id, to_article_id=None).count()
    return render_template("ai/detail.html", ai_kb=ai_kb, sources=sources, articles=articles, redlinks=redlinks)


@bp.route("/<ai_kb_id>/edit", methods=["GET", "POST"])
@login_required
def edit_ai_kb(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    if request.method == "GET":
        return render_template("ai/edit.html", ai_kb=ai_kb)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("名称不能为空", "error")
        return redirect(url_for("ai.edit_ai_kb", ai_kb_id=ai_kb.id))
    ai_kb.name = name
    ai_kb.description = (request.form.get("description") or "").strip()
    ai_kb.chat_model = (request.form.get("chat_model") or "").strip()
    ai_kb.enable_rag = bool(request.form.get("enable_rag"))
    db.session.commit()
    flash("已保存", "success")
    return redirect(url_for("ai.detail", ai_kb_id=ai_kb.id))


@bp.route("/<ai_kb_id>/delete", methods=["POST"])
@login_required
def delete_ai_kb(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    name = ai_kb.name
    # 清理本地 Wiki 目录（DB 层已 cascade，文件需手动清）
    try:
        import shutil
        from pathlib import Path
        wiki_dir = Path(current_app.config["AI_WIKI_DIR"]) / str(ai_kb.id)
        if wiki_dir.exists():
            shutil.rmtree(wiki_dir, ignore_errors=True)
    except Exception:
        current_app.logger.exception("清理 AI Wiki 目录失败")
    db.session.delete(ai_kb)
    db.session.commit()
    flash(f"已删除 AI 知识库『{name}』", "info")
    return redirect(url_for("ai.index"))


# ---------- Sources ----------

@bp.route("/<ai_kb_id>/sources")
@login_required
def sources(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    existing_doc_ids = {s.doc_id for s in AIKBSource.query.filter_by(ai_kb_id=ai_kb.id).all()}
    # 按原始知识库分组（自有 + 可访问）
    my_kbs = kb_service.list_my_kbs(current_user).all()
    kb_docs: dict[str, list] = {}
    for kb in my_kbs:
        docs = (
            Document.query.filter_by(kb_id=kb.id, is_deleted=False)
            .order_by(Document.updated_at.desc()).all()
        )
        if docs:
            kb_docs[kb.name] = docs
    return render_template("ai/sources.html", ai_kb=ai_kb,
                           existing_doc_ids=existing_doc_ids, kb_docs=kb_docs)


@bp.route("/<ai_kb_id>/sources/add", methods=["POST"])
@login_required
def add_sources(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    doc_ids = [x.strip() for x in request.form.getlist("doc_ids") if x and x.strip()]
    added = 0
    for did in doc_ids:
        doc = db.session.get(Document, did)
        if not doc or doc.is_deleted:
            continue
        if not kb_service.can_access(current_user, doc.kb):
            continue
        if AIKBSource.query.filter_by(ai_kb_id=ai_kb.id, doc_id=did).first():
            continue
        db.session.add(AIKBSource(ai_kb_id=ai_kb.id, doc_id=did))
        added += 1
    db.session.commit()
    flash(f"已加入 {added} 篇文档", "success")
    return redirect(url_for("ai.sources", ai_kb_id=ai_kb.id))


@bp.route("/<ai_kb_id>/sources/upload", methods=["POST"])
@login_required
def upload_source(ai_kb_id):
    """上传 PDF / Word / 文本 / 图片 作为源文档。支持多文件。"""
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    files = request.files.getlist("files") or ([request.files.get("file")] if request.files.get("file") else [])
    files = [f for f in files if f and f.filename]
    if not files:
        flash("请选择要上传的文件", "error")
        return redirect(url_for("ai.sources", ai_kb_id=ai_kb.id))

    base_dir = Path(current_app.instance_path) / "ai_uploads" / str(ai_kb.id)
    base_dir.mkdir(parents=True, exist_ok=True)

    added, skipped = 0, []
    for f in files:
        original = f.filename or ""
        if not is_supported(original):
            skipped.append(f"{original}（不支持的格式）")
            continue
        safe = secure_filename(original) or "upload"
        # 保证扩展名被保留（secure_filename 可能处理后丢掉）
        ext = Path(original).suffix.lower()
        if not safe.lower().endswith(ext):
            safe = f"{safe}{ext}"
        unique = f"{uuid.uuid4().hex}_{safe}"
        full_path = base_dir / unique
        f.save(str(full_path))
        try:
            size = full_path.stat().st_size
        except OSError:
            size = 0
        # upload_path 存相对 instance_path 的路径，与 ai_service 拼接逻辑一致
        rel_path = str(Path("ai_uploads") / str(ai_kb.id) / unique).replace("\\", "/")
        src = AIKBSource(
            ai_kb_id=ai_kb.id,
            kind=AIKBSourceKind.UPLOAD.value,
            doc_id=None,
            upload_filename=original,
            upload_path=rel_path,
            upload_ext=ext,
            upload_bytes=size,
        )
        db.session.add(src)
        added += 1
    db.session.commit()

    if added:
        flash(f"已上传 {added} 个文件，正在启动 Wiki 处理", "success")
        ai_service.build_wiki_async(current_app._get_current_object(), ai_kb.id, only_pending=True)
    if skipped:
        flash("已跳过：" + "、".join(skipped), "warning")
    return redirect(url_for("ai.sources", ai_kb_id=ai_kb.id))


@bp.route("/<ai_kb_id>/sources/<source_id>/remove", methods=["POST"])
@login_required
def remove_source(ai_kb_id, source_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    src = db.session.get(AIKBSource, source_id)
    if src and src.ai_kb_id == ai_kb.id:
        # 上传件：同时清理本地文件
        if src.kind == AIKBSourceKind.UPLOAD.value and src.upload_path:
            try:
                up = Path(src.upload_path)
                full = up if up.is_absolute() else (Path(current_app.instance_path) / up)
                if full.exists() and full.is_file():
                    full.unlink()
            except Exception:
                current_app.logger.exception("清理上传文件失败")
        db.session.delete(src)
        db.session.commit()
        flash("已移除", "info")
    nxt = (request.form.get("next") or "").strip()
    if nxt == "detail":
        return redirect(url_for("ai.detail", ai_kb_id=ai_kb.id))
    return redirect(url_for("ai.sources", ai_kb_id=ai_kb.id))


@bp.route("/<ai_kb_id>/sources/<source_id>/retry", methods=["POST"])
@login_required
def retry_source(ai_kb_id, source_id):
    """重置失败/单条源文档为 pending 并触发增量构建。"""
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    src = db.session.get(AIKBSource, source_id)
    if not src or src.ai_kb_id != ai_kb.id:
        abort(404)
    src.status = AIKBSourceStatus.PENDING.value
    src.err_msg = None
    # 若整体处于失败状态，重试单条时一并清掉整体错误，避免误导
    if ai_kb.status == AIKBStatus.FAILED.value:
        ai_kb.error_msg = None
    db.session.commit()
    if ai_kb.status == AIKBStatus.BUILDING.value:
        flash("已重置该文档为待处理，当前正在构建中将自动处理", "success")
    else:
        ai_service.build_wiki_async(current_app._get_current_object(), ai_kb.id, only_pending=True)
        flash("已开始重试该文档的 Wiki 生成", "success")
    nxt = (request.form.get("next") or "").strip()
    if nxt == "sources":
        return redirect(url_for("ai.sources", ai_kb_id=ai_kb.id))
    return redirect(url_for("ai.detail", ai_kb_id=ai_kb.id))


# ---------- Build / Status ----------

@bp.route("/<ai_kb_id>/build", methods=["POST"])
@login_required
def build(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    if ai_kb.status == AIKBStatus.BUILDING.value:
        flash("正在生成，请稍候", "warning")
        return redirect(url_for("ai.detail", ai_kb_id=ai_kb.id))
    only_pending = request.form.get("scope") != "all"
    if not only_pending:
        AIKBSource.query.filter_by(ai_kb_id=ai_kb.id).update({"status": AIKBSourceStatus.PENDING.value})
        db.session.commit()
    ai_service.build_wiki_async(current_app._get_current_object(), ai_kb.id, only_pending=True)
    flash("Wiki 生成任务已启动，刷新页面查看进度", "success")
    return redirect(url_for("ai.detail", ai_kb_id=ai_kb.id))


@bp.route("/<ai_kb_id>/status")
@login_required
def status(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    counts = {
        s.value: AIKBSource.query.filter_by(ai_kb_id=ai_kb.id, status=s.value).count()
        for s in AIKBSourceStatus
    }
    return jsonify({
        "status": ai_kb.status,
        "error": ai_kb.error_msg or "",
        "last_built_at": ai_kb.last_built_at.isoformat() if ai_kb.last_built_at else None,
        "sources": counts,
        "articles": AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).count(),
    })


# ---------- Wiki browse ----------

def _wiki_resolver(ai_kb_id):
    return ai_service.article_resolver(ai_kb_id)


def _rewrite_wiki_links(html: str, ai_kb_id) -> str:
    """Replace href="#WIKI:slug" -> actual URL."""
    import re
    pattern = re.compile(r'href="#WIKI:([^"\s]+)"')

    def sub(m):
        slug = m.group(1)
        return f'href="{url_for("ai.wiki_article", ai_kb_id=ai_kb_id, slug=slug)}" class="wiki-link"'

    return pattern.sub(sub, html)


@bp.route("/<ai_kb_id>/wiki")
@login_required
def wiki_home(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    articles = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).order_by(AIKBArticle.title.asc()).all()
    # tag groups
    tag_groups: dict[str, list] = {}
    for a in articles:
        tags = json.loads(a.tags_json or "[]") or ["未分类"]
        for t in tags:
            tag_groups.setdefault(t, []).append(a)
    return render_template("ai/wiki_home.html", ai_kb=ai_kb, articles=articles, tag_groups=tag_groups)


@bp.route("/<ai_kb_id>/wiki/<slug>")
@login_required
def wiki_article(ai_kb_id, slug):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    article = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id, slug=slug).first()
    if not article:
        abort(404)
    resolver = _wiki_resolver(ai_kb.id)
    html = render_wiki_markdown(article.content_md or "", resolver)
    html = _rewrite_wiki_links(html, ai_kb.id)
    backlinks = (
        AIKBLink.query.filter_by(ai_kb_id=ai_kb.id, to_article_id=article.id).all()
    )
    backlink_articles = []
    seen = set()
    for l in backlinks:
        if l.from_article_id in seen:
            continue
        seen.add(l.from_article_id)
        a = db.session.get(AIKBArticle, l.from_article_id)
        if a:
            backlink_articles.append(a)
    articles = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).order_by(AIKBArticle.title.asc()).all()
    tags = json.loads(article.tags_json or "[]")
    return render_template(
        "ai/wiki_article.html",
        ai_kb=ai_kb, article=article, html=html,
        articles=articles, backlinks=backlink_articles, tags=tags,
    )


@bp.route("/<ai_kb_id>/wiki/<slug>/regenerate", methods=["POST"])
@login_required
def regenerate_article(ai_kb_id, slug):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    article = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id, slug=slug).first()
    if not article:
        abort(404)
    ai_service.regenerate_one_async(current_app._get_current_object(), ai_kb.id, article.id)
    flash("条目重生任务已启动", "success")
    return redirect(url_for("ai.wiki_article", ai_kb_id=ai_kb.id, slug=slug))


@bp.route("/<ai_kb_id>/graph")
@login_required
def graph(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    articles = AIKBArticle.query.filter_by(ai_kb_id=ai_kb.id).all()
    links = AIKBLink.query.filter_by(ai_kb_id=ai_kb.id).filter(AIKBLink.to_article_id != None).all()
    nodes = [{"id": a.id, "label": a.title, "slug": a.slug} for a in articles]
    edges = [{"from": l.from_article_id, "to": l.to_article_id} for l in links]
    return render_template("ai/graph.html", ai_kb=ai_kb,
                           graph_data={"nodes": nodes, "edges": edges})


# ---------- Optional chat (RAG / plain) ----------

@bp.route("/<ai_kb_id>/chat", methods=["GET", "POST"])
@login_required
def chat(ai_kb_id):
    ai_kb = _get_ai_kb_or_404(ai_kb_id)
    if request.method == "POST":
        q = (request.form.get("q") or "").strip()
        if not q:
            return jsonify({"ok": False, "error": "请输入问题"})
        try:
            answer = ai_service.chat_with_wiki(ai_kb, q)
            return jsonify({"ok": True, "answer": answer})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    return render_template("ai/chat.html", ai_kb=ai_kb)

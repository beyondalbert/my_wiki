"""上传源文档抽取：把 PDF / Word / 文本 / 图片统一抽取为纯文本。

供 AI 知识库 Wiki 化前置抽取使用。图片走多模态 LLM。
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)


SUPPORTED_TEXT_EXTS = {".txt", ".md", ".markdown"}
SUPPORTED_PDF_EXTS = {".pdf"}
SUPPORTED_DOCX_EXTS = {".docx"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

ALL_SUPPORTED_EXTS = (
    SUPPORTED_TEXT_EXTS | SUPPORTED_PDF_EXTS | SUPPORTED_DOCX_EXTS | SUPPORTED_IMAGE_EXTS
)


def is_supported(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in ALL_SUPPORTED_EXTS


def kind_of(filename: str) -> str:
    """返回粗类型：text / pdf / docx / image / unknown。"""
    ext = Path(filename or "").suffix.lower()
    if ext in SUPPORTED_TEXT_EXTS:
        return "text"
    if ext in SUPPORTED_PDF_EXTS:
        return "pdf"
    if ext in SUPPORTED_DOCX_EXTS:
        return "docx"
    if ext in SUPPORTED_IMAGE_EXTS:
        return "image"
    return "unknown"


def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader  # type: ignore
    reader = PdfReader(file_path)
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:  # pragma: no cover
            logger.warning("PDF page extract failed: %s", e)
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    return text


def _extract_docx(file_path: str) -> str:
    from docx import Document as DocxDoc  # type: ignore
    d = DocxDoc(file_path)
    parts: list[str] = []
    for p in d.paragraphs:
        if p.text and p.text.strip():
            parts.append(p.text.strip())
    # 表格也尽量抽出来
    for tbl in d.tables:
        for row in tbl.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_text_file(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8", errors="ignore")


IMAGE_OCR_PROMPT = (
    "请仔细阅读这张图片，将其中所有的文字、数据、图表要点、关键信息以纯文本/Markdown 形式逐项输出。"
    "如果是流程图或架构图，描述其结构与节点关系。"
    "不要解释，不要回答你看到了什么，直接给出可被后续 wiki 化处理的事实性内容。"
)


def _extract_image_with_llm(file_path: str, llm) -> str:
    """通过多模态 LLM 抽取图片内容为文字。

    要求 llm 是 services.ai_service.LLMClient 实例，model 应支持 vision。
    """
    if llm is None:
        raise RuntimeError("图片源文档需要多模态 LLM，但未注入 LLMClient")
    p = Path(file_path)
    mime, _ = mimetypes.guess_type(p.name)
    if not mime:
        mime = "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    return llm.chat_with_image(IMAGE_OCR_PROMPT, data_url)


def extract_text_from_upload(file_path: str, original_name: str, llm=None) -> str:
    """根据扩展名分发到对应抽取器，返回纯文本。

    file_path: 服务器本地路径
    original_name: 用户上传时的原始文件名（决定扩展名）
    llm: services.ai_service.LLMClient，仅图片需要
    """
    if not Path(file_path).exists():
        raise RuntimeError(f"文件不存在: {file_path}")
    k = kind_of(original_name)
    if k == "text":
        text = _extract_text_file(file_path)
    elif k == "pdf":
        text = _extract_pdf(file_path)
    elif k == "docx":
        text = _extract_docx(file_path)
    elif k == "image":
        text = _extract_image_with_llm(file_path, llm)
    else:
        raise RuntimeError(
            f"不支持的文件格式：{Path(original_name).suffix or '<空>'}；"
            f"当前支持 PDF / Word(.docx) / 文本(.txt/.md) / 图片"
        )
    text = (text or "").strip()
    if not text:
        raise RuntimeError("抽取结果为空，文件可能是扫描件、加密或内容为空")
    return text

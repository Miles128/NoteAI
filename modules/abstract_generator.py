import logging
from pathlib import Path
from config import config
from prompts import ABSTRACT_PROMPT

logger = logging.getLogger(__name__)


class AbstractGenerator:
    """综述生成器"""

    def generate(self, topic_name: str, topic_path: str, level: int, workspace: str) -> dict:
        """为指定主题生成综述

        Args:
            topic_name: 主题名称
            topic_path: 主题文件夹路径
            level: 主题层级（1 或 2）
            workspace: 工作区路径

        Returns:
            {"success": bool, "message": str, "file": str}
        """
        # 收集所有文章
        articles = self._collect_articles(topic_path, workspace)
        if not articles:
            return {"success": False, "message": "该主题下没有文章"}

        # 调用 LLM
        abstract_text = self._call_llm(topic_name, articles)
        if not abstract_text:
            return {"success": False, "message": "AI 生成失败"}

        # 写入文件
        abstract_file = Path(topic_path) / "综述.md"
        try:
            content = f"# {topic_name} 综述\\n\\n> 自动生成，最后更新: -\\n\\n{abstract_text}"
            abstract_file.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "message": f"综述已生成: 综述.md",
                "file": str(abstract_file),
                "preview": abstract_text[:200] + "...",
            }
        except Exception as e:
            return {"success": False, "message": f"写入失败: {e}"}

    def _collect_articles(self, topic_path: str, workspace: str) -> list[dict]:
        """收集主题文件夹下所有文章正文"""
        articles = []
        p = Path(topic_path)
        if not p.exists():
            return articles

        for f in p.glob("**/*.md"):
            if f.name in ("综述.md", "WIKI.md", "tags.md"):
                continue
            try:
                text = f.read_text(encoding="utf-8")
                # 只取前 2000 字作为摘要
                articles.append({
                    "title": f.stem,
                    "content": text[:2000],
                })
                if len(articles) >= 50:
                    break  # 最多 50 篇
            except Exception as e:
                logger.warning(f"读取文件失败 {f}: {e}")
                continue

        return articles

    def _call_llm(self, topic_name: str, articles: list[dict]) -> str:
        """调用 LLM 生成综述"""
        try:
            from langchain_openai import ChatOpenAI

            article_texts = []
            for i, a in enumerate(articles, 1):
                article_texts.append(f"{i}. **{a['title']}**\\n{a['content'][:500]}\\n")

            prompt = ABSTRACT_PROMPT.format(
                articles="\\n---\\n".join(article_texts)
            )

            llm = ChatOpenAI(
                model=config.model_name,
                api_key=config.api_key,
                base_url=config.api_base,
                temperature=0.3,
                max_tokens=1000,
            )

            response = llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)

        except ImportError:
            logger.warning("[abstract] langchain_openai 不可用，使用占位综述")
            return self._fallback_summary(topic_name, articles)
        except Exception as e:
            logger.error(f"[abstract] LLM 调用失败: {e}")
            return self._fallback_summary(topic_name, articles)

    def _fallback_summary(self, topic_name: str, articles: list[dict]) -> str:
        """LLM 不可用时的占位综述"""
        lines = [
            f"## {topic_name}",
            "",
            f"本主题共包含 {len(articles)} 篇文章。",
            "",
            "### 文章列表",
            "",
        ]
        for a in articles[:20]:
            lines.append(f"- {a['title']}")
        if len(articles) > 20:
            lines.append(f"- ... 还有 {len(articles) - 20} 篇")
        return "\\n".join(lines)

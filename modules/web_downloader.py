import requests
import time
import re
from typing import List, Dict, Optional, Callable
from pathlib import Path
from urllib.parse import urlparse, urljoin
from markdownify import markdownify as md
from bs4 import BeautifulSoup
from readability import Document
import validators

from config.settings import config
from utils.logger import logger
from utils.helpers import (
    sanitize_filename, clean_text, remove_images_from_markdown,
    extract_title_from_markdown, ensure_dir, is_valid_url, retry_on_failure,
    check_api_config, APIConfigError, NetworkError, is_network_error,
    smart_format_markdown
)
from utils.tag_extractor import (
    extract_tags_from_filename,
    add_yaml_frontmatter_to_content,
    add_yaml_frontmatter_to_file
)


class WebDownloader:
    """网页下载器"""
    
    def __init__(self, progress_callback: Optional[Callable] = None, ai_assist: bool = False, include_images: bool = False):
        """
        初始化网页下载器
        
        Args:
            progress_callback: 进度回调函数
            ai_assist: 是否使用AI进行额外优化（默认False）
            include_images: 是否在Markdown中保留图片的外部 URL 链接（默认False，不下载图片到本地）
        """
        self.progress_callback = progress_callback
        self.ai_assist = ai_assist
        self.include_images = include_images
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def _extract_title(self, html_content: str, doc_title: str = "", url: str = "") -> str:
        """
        从HTML内容中提取文章标题
        使用多种策略确保能获取到有效的标题
        针对微信公众号、小红书、知乎等平台优化
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        meta_selectors = [
            'meta[property="og:title"]',
            'meta[name="twitter:title"]',
            'meta[property="twitter:title"]',
            'meta[name="activity-name"]',
            'meta[property="activity-name"]',
            'meta[property="wx:title"]',
            'meta[name="xhs_title"]',
            'meta[property="xhs:title"]',
            'meta[name="red:title"]',
            'meta[property="zhihu:title"]',
            'meta[property="weibo:article:title"]',
            'meta[property="article:title"]',
            'meta[property="wapcant:title"]',
            'meta[itemprop="headline"]',
            'meta[name="title"]',
            'meta[property="title"]',
        ]
        for selector in meta_selectors:
            meta = soup.select_one(selector)
            if meta:
                content = meta.get('content', '').strip()
                if content:
                    return content
        
        doc_title_stripped = doc_title.strip() if doc_title else ""
        invalid_titles = {"no title", "未命名文章", ""}
        if doc_title_stripped.lower() not in invalid_titles:
            return doc_title_stripped
        
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            for sep in [' - ', ' – ', ' — ', ' | ', ' » ', ' :: ', ' · ', ' _ ', ' – ']:
                if sep in title:
                    title = title.split(sep)[0].strip()
            if title:
                return title
        
        h1 = soup.find('h1')
        if h1 and h1.get_text().strip():
            return h1.get_text().strip()
        
        wechat_selectors = [
            '#activity-name',
            '.activity-name',
            '#js_title',
            '.wx-rb__title',
            '.article-title',
            '.weui-article__title',
        ]
        for selector in wechat_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text().strip()
                if text and text not in invalid_titles:
                    return text
        
        xiaohongshu_selectors = [
            '.xiaohongshu-title',
            '.red-title',
            '[data-v-title]',
            '.title-wrapper',
            '.note-content-title',
            '.content-title',
        ]
        for selector in xiaohongshu_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text().strip()
                if text and text not in invalid_titles:
                    return text
        
        zhihu_selectors = [
            'meta[itemprop="name"]',
            '.Post-Title',
            '.QuestionHeader-title',
            '.question-title',
            '[itemprop="headline"]',
        ]
        for selector in zhihu_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text().strip() if hasattr(elem, 'get_text') else elem.get('content', '').strip()
                if text and text not in invalid_titles:
                    return text
        
        article = soup.find('article') or soup.find('main')
        if article:
            for tag in ['h1', 'h2', 'h3']:
                elem = article.find(tag)
                if elem:
                    text = elem.get_text().strip()
                    if text and text not in invalid_titles:
                        return text
        
        common_selectors = [
            '.post-title', '.entry-title', '.article-title', '.headline',
            '#post-title', '#entry-title', '#article-title', '#headline',
            '.title', '#title', '.post-header h2', '.entry-title',
        ]
        for selector in common_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text().strip()
                if text and text not in invalid_titles:
                    return text
        
        for tag in ['h2', 'h3', 'h4']:
            elem = soup.find(tag)
            if elem:
                text = elem.get_text().strip()
                if text and text not in invalid_titles:
                    return text
        
        if url:
            try:
                from urllib.parse import urlparse, unquote
                path = unquote(urlparse(url).path)
                if path:
                    last_part = path.rstrip('/').split('/')[-1]
                    if last_part:
                        title = last_part.replace('-', ' ').replace('_', ' ').replace('.html', '').replace('.htm', '')
                        if title:
                            return title[:100]
            except Exception:
                pass
        
        return "未命名文章"
    
    def _normalize_img_tags_in_html(self, html_content: str, base_url: str) -> str:
        """
        规范化HTML中的img标签，处理懒加载属性并将相对路径转换为绝对URL
        
        处理的懒加载属性：
        - data-src
        - data-original
        - data-srcset
        - srcset
        
        Args:
            html_content: HTML内容
            base_url: 基础URL
            
        Returns:
            处理后的HTML内容，所有img标签都有正确的src属性
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        lazy_load_attributes = [
            'data-src',
            'data-original',
            'data-srcset',
            'data-url',
            'data-lazy-src',
            'data-lazy',
            'data-actual-src',
            'data-real-src',
        ]
        
        img_count = 0
        processed_count = 0
        
        for img in soup.find_all('img'):
            img_count += 1
            actual_src = None
            
            for attr in lazy_load_attributes:
                if img.get(attr):
                    attr_value = img.get(attr)
                    if attr in ['data-srcset', 'srcset']:
                        srcset_urls = self._parse_srcset(attr_value)
                        if srcset_urls:
                            actual_src = srcset_urls[0]
                            break
                    else:
                        actual_src = attr_value
                        break
            
            if actual_src is None:
                srcset = img.get('srcset')
                if srcset:
                    srcset_urls = self._parse_srcset(srcset)
                    if srcset_urls:
                        actual_src = srcset_urls[0]
            
            if actual_src is None:
                actual_src = img.get('src')
            
            if actual_src:
                try:
                    absolute_url = urljoin(base_url, actual_src)
                    img['src'] = absolute_url
                    
                    for attr in lazy_load_attributes:
                        if attr in img.attrs:
                            del img[attr]
                    if 'srcset' in img.attrs:
                        del img['srcset']
                    if 'data-srcset' in img.attrs:
                        del img['data-srcset']
                    
                    processed_count += 1
                    logger.debug(f"图片URL已规范化: {actual_src} -> {absolute_url}")
                except Exception as e:
                    logger.warning(f"图片URL处理失败: {actual_src}, 错误: {e}")
        
        logger.info(f"HTML中找到 {img_count} 个图片，已处理 {processed_count} 个")
        return str(soup)
    
    def _parse_srcset(self, srcset_value: str) -> List[str]:
        """
        解析 srcset 属性，提取所有图片URL
        
        srcset 格式示例:
        - "image1.jpg 1x, image2.jpg 2x"
        - "image1.jpg 300w, image2.jpg 600w"
        
        Args:
            srcset_value: srcset 属性值
            
        Returns:
            图片URL列表，按尺寸从小到大排列
        """
        if not srcset_value:
            return []
        
        urls = []
        parts = srcset_value.split(',')
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            tokens = part.split()
            if tokens:
                url = tokens[0]
                if url:
                    urls.append(url)
        
        return urls
    
    def _normalize_image_urls_in_markdown(self, markdown_content: str, base_url: str) -> str:
        """
        将Markdown中的相对路径图片URL转换为绝对URL
        
        Args:
            markdown_content: 原始Markdown内容
            base_url: 基础URL
            
        Returns:
            处理后的Markdown内容，图片链接均为绝对URL
        """
        import re
        
        img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        
        def replace_image(match):
            alt_text = match.group(1)
            img_url = match.group(2)
            
            if img_url.startswith(('http://', 'https://', 'data:')):
                return match.group(0)
            
            try:
                absolute_url = urljoin(base_url, img_url)
                logger.info(f"图片URL已规范化: {img_url} -> {absolute_url}")
                return f"![{alt_text}]({absolute_url})"
            except Exception as e:
                logger.warning(f"图片URL规范化失败: {img_url}, 错误: {e}")
                return match.group(0)
        
        result = re.sub(img_pattern, replace_image, markdown_content)
        
        return result
    
    def _count_images_in_markdown(self, markdown_content: str) -> int:
        """统计Markdown中的图片数量"""
        import re
        img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        matches = list(re.finditer(img_pattern, markdown_content))
        return len(matches)
    
    def download_article(self, url: str) -> Dict:
        """下载单篇文章"""
        result = {
            'url': url,
            'success': False,
            'title': '',
            'content': '',
            'error': None,
            'file_path': None
        }
        
        try:
            if not is_valid_url(url):
                result['error'] = "无效的URL"
                return result
            
            logger.info(f"开始下载: {url}")
            
            response = self._get_with_retry(url)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            
            html_content = response.text
            
            if self.include_images:
                logger.info("正在预处理HTML中的图片标签...")
                html_content = self._normalize_img_tags_in_html(html_content, url)
            
            doc = Document(html_content)
            doc_title = doc.title() or ""
            summary_html = doc.summary()

            title = self._extract_title(html_content, doc_title, url)

            markdown_content = self._convert_standard(summary_html, title)
            
            img_count_after_convert = self._count_images_in_markdown(markdown_content)
            logger.info(f"markdownify转换后: {img_count_after_convert} 个图片链接")
            
            markdown_content = clean_text(markdown_content)
            
            img_count_after_clean = self._count_images_in_markdown(markdown_content)
            logger.info(f"clean_text后: {img_count_after_clean} 个图片链接")

            markdown_content = smart_format_markdown(markdown_content, title)

            img_count_after_optimize = self._count_images_in_markdown(markdown_content)
            logger.info(f"格式化后: {img_count_after_optimize} 个图片链接")

            if self.include_images:
                logger.info("保留图片URL链接...")
                markdown_content = self._normalize_image_urls_in_markdown(markdown_content, url)
                
                final_img_count = self._count_images_in_markdown(markdown_content)
                logger.info(f"最终图片数量: {final_img_count} 个")
            else:
                logger.info("移除图片...")
                markdown_content = remove_images_from_markdown(markdown_content)

            result['success'] = True
            result['title'] = title
            result['content'] = markdown_content

            logger.info(f"下载成功: {title}")

        except requests.RequestException as e:
            result['error'] = f"网络请求失败: {str(e)}"
            logger.error(f"下载失败 {url}: {e}")
        except Exception as e:
            result['error'] = f"处理失败: {str(e)}"
            logger.error(f"处理失败 {url}: {e}")

        return result

    def _convert_standard(self, html_content: str, title: str) -> str:
        """标准模式：使用 markdownify 转换网页为 Markdown"""
        markdown = md(html_content, heading_style="ATX")
        markdown = clean_text(markdown)
        has_title = False
        for line in markdown.split('\n'):
            stripped = line.strip()
            if stripped.startswith('# ') or stripped.startswith('## '):
                has_title = True
                break
        if not has_title:
            markdown = f"# {title}\n\n{markdown}"
        return markdown
    
    @retry_on_failure(max_retries=3, delay=1.0)
    def _get_with_retry(self, url: str) -> requests.Response:
        """带重试的GET请求"""
        return self.session.get(url, timeout=config.timeout, allow_redirects=True)
    
    def download_batch(
        self, 
        urls: List[str], 
        save_path: str,
    ) -> List[Dict]:
        """批量下载文章"""
        results = []
        notes_dir = Path(save_path) / "Notes"
        save_dir = ensure_dir(str(notes_dir))
        
        total = len(urls)
        for i, url in enumerate(urls):
            url = url.strip()
            if not url:
                continue
            
            if self.progress_callback:
                self.progress_callback(i, total, f"正在下载第 {i + 1}/{total} 篇...")
            
            result = self.download_article(url)
            
            if result['success']:
                article_title = result.get('title', '未命名文章')
                if self.progress_callback:
                    self.progress_callback(i + 1, total, f"正在保存: {article_title}")
                
                filename = sanitize_filename(article_title) + '.md'
                file_path = save_dir / filename

                try:
                    content_with_frontmatter = add_yaml_frontmatter_to_content(
                        result['content'],
                        title=article_title,
                        tags=[],
                        source=url
                    )
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content_with_frontmatter)

                    tags = extract_tags_from_filename(str(file_path))
                    if tags:
                        add_yaml_frontmatter_to_file(str(file_path), tags=tags, source=url)

                    try:
                        from utils.topic_assigner import auto_assign_topic_for_file
                        auto_assign_topic_for_file(str(file_path))
                    except Exception:
                        pass

                    result['file_path'] = str(file_path)
                    result['tags'] = tags
                    logger.info(f"已保存: {file_path}")
                except Exception as e:
                    result['error'] = f"保存失败: {str(e)}"
                    logger.error(f"保存失败: {e}")
            else:
                if self.progress_callback:
                    self.progress_callback(i + 1, total, f"下载失败: {url}")
            
            results.append(result)
            
            if i < total - 1:
                time.sleep(1)
        
        if self.progress_callback:
            success_count = sum(1 for r in results if r['success'])
            self.progress_callback(total, total, f"下载完成: {success_count}/{total} 篇成功")

        try:
            from config import config
            from utils.tag_extractor import save_tags_md
            if config.workspace_path:
                save_tags_md(config.workspace_path)
        except Exception:
            pass

        return results

    def _convert_with_markdownify(self, html_content: str) -> str:
        """使用markdownify转换HTML到Markdown"""
        return md(html_content, heading_style="ATX")

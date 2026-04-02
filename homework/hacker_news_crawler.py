import asyncio
import time
from os import makedirs

from bs4 import BeautifulSoup

from log import logger
import aiohttp
import aiofiles
from models.post import Post


class HackerNewsCrawler:
    def __init__(self, t: int = 30):
        self.url = "https://news.ycombinator.com/"
        self.semaphore = asyncio.Semaphore(20)
        self.session = None
        self.seen_links = set()
        self.t = t
        self.metrics = {
            "posts_total": 0,
            "posts_new": 0,
            "pages_fetched": 0,
            "errors": 0,
            "duration": 0
        }

    async def crawl(self):
        async with aiohttp.ClientSession() as session:
            while True:
                self.metrics["posts_new"] = 0
                start = time.perf_counter()
                self.session = session
                logger.info(f"Scraping {self.url}")
                posts = await self.parse_posts()
                await self.save_post(posts)
                logger.info(f"Saved posts: {len(posts)}")
                self.metrics["duration"] = time.perf_counter() - start
                logger.info(
                    f"Metrics: new={self.metrics['posts_new']} | "
                    f"total={self.metrics['posts_total']} | "
                    f"pages={self.metrics['pages_fetched']} | "
                    f"errors={self.metrics['errors']} | "
                    f"time={self.metrics['duration']:.2f}s"
                )
                await asyncio.sleep(self.t)



    async def process_post(self, title, link, comments_url):
        html_task = self.fetch_page(link)
        comments_task = self.extract_comments(comments_url)

        html, comment_links = await asyncio.gather(
            html_task,
            comments_task
        )

        comment_tasks = [
            self.fetch_page(url) for url in comment_links
        ]

        html_comments = await asyncio.gather(*comment_tasks)
        return Post(
            title=title,
            link=link,
            comments=html_comments,
            html=html,
        )

    async def save_post(self, posts: list[Post]) -> None:
        for post in posts:
            self.metrics["posts_total"] += 1
            directory = self.create_directory(post.title)
            await self.create_file(f"{directory}/index.html", post.html)
            for index, comment in enumerate(post.comments):
                await self.create_file(f"{directory}/comment_{index}.html", comment)

    async def extract_comments(self, comment_url):
        links = []
        soup = BeautifulSoup(await self.fetch_page(self.url+comment_url), "html.parser")
        table = soup.find("table", class_="comment-tree")
        if not table:
            logger.info(f"No table in page {self.url+comment_url}")
            return []
        comments = table.find_all("tr", class_="athing")
        if not comments:
            logger.info(f"No comments in page {self.url+comment_url}")
        for comment in comments[:30]:
            comment_text = comment.find("div", class_="commtext")
            if not comment_text:
                continue
            link_tag = comment_text.find("a")
            if link_tag and link_tag.get("href"):
                links.append(link_tag["href"])
        return links


    async def parse_posts(self):
        tasks = []
        bs = BeautifulSoup(await self.fetch_page(self.url), "html.parser")
        container = bs.find("tr", id="bigbox")
        if not container:
            return []
        table = container.find("table")
        if not table:
            return []
        posts = table.find_all("tr", class_="athing") or []
        for post in posts[:30]:
            title_tag = post.select_one(".titleline a")
            title = title_tag.get_text(strip=True).replace("/", " ")
            if title in self.seen_links:
                logger.debug(f"Skipping post {title}, already seen")
                continue
            self.metrics["posts_new"] += 1
            self.seen_links.add(title)
            link = title_tag["href"]
            metadata = post.find_next_sibling("tr")
            comments = metadata.find_all("a")[-1].get("href")
            tasks.append(self.process_post(title, link, comments))
        results = await asyncio.gather(*tasks)
        return results
    @staticmethod
    async def create_file(path: str, data: str) -> None:
        logger.debug("Creating file: %s", path)
        async with aiofiles.open(path, "w") as file:
            await file.write(data)
    @staticmethod
    def create_directory(name: str) -> str:
        logger.debug(f"Creating directory {name}")
        makedirs(f"results/{name}", exist_ok=True)
        return f"results/{name}/"

    async def fetch_page(self, url):
        async with self.semaphore:
            try:
                async with self.session.get(url, timeout=10) as response:
                    if response.status == 200:
                        self.metrics["pages_fetched"] += 1
                        return await response.text(
                            encoding="utf-8",
                            errors="ignore"
                        )
            except Exception as e:
                self.metrics["errors"] += 1
                logger.exception(f"Error fetching page {e}")
                return ""
            return ""


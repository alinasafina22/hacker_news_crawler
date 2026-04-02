import asyncio
from hacker_news_crawler import HackerNewsCrawler



if __name__ == '__main__':
    crawler = HackerNewsCrawler()
    asyncio.run(crawler.crawl())
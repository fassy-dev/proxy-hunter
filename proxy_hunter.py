import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

class Config:
    SOURCE_URL = "https://free-proxy-list.net"
    TEST_URL = "https://httpbin.org"
    TIMEOUT = 4
    MAX_WORKERS = 50
    OUTPUT_FILE = "valid_proxies.txt"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

class ProxyParser:
    def __init__(self, config: Config):
        self.config = config

    def fetch_raw_proxies(self) -> list[str]:
        logging.info("Подключение к источнику %s...", self.config.SOURCE_URL)
        try:
            response = requests.get(
                self.config.SOURCE_URL, 
                headers=self.config.HEADERS, 
                timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as err:
            logging.error("Не удалось загрузить страницу: %s", err)
            return []

        return self._parse_html(response.text)

    def _parse_html(self, html_content: str) -> list[str]:
        soup = BeautifulSoup(html_content, 'html.parser')
        proxies = []

        textarea = soup.find("textarea", readonly=True)
        if textarea and textarea.text:
            proxies = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+", textarea.text)
            if proxies:
                logging.info("Извлечено %d прокси из блока Raw List.", len(proxies))
                return proxies

        table = soup.find("table", class_="table-striped")
        if not table:
            logging.warning("Не удалось найти блоки с прокси на странице.")
            return []

        rows = table.find_all("tr")[1:]
        for row in rows:
            tds = row.find_all("td")
            if len(tds) >= 2:
                ip = tds[0].text.strip()
                port = tds[1].text.strip()
                if ip and port:
                    proxies.append(f"{ip}:{port}")

        logging.info("Собрано %d потенциальных прокси из таблицы.", len(proxies))
        return proxies

class ProxyChecker:
    def __init__(self, config: Config):
        self.config = config

    def check_single_proxy(self, proxy: str) -> str | None:
        proxy_dict = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        with requests.Session() as session:
            session.proxies = proxy_dict
            try:
                response = session.get(
                    self.config.TEST_URL, 
                    headers=self.config.HEADERS, 
                    timeout=self.config.TIMEOUT
                )
                if response.status_code == 200:
                    logging.info("[ ВАЛИДНЫЙ ] %s", proxy)
                    return proxy
            except requests.RequestException:
                pass
        return None

class Application:
    def __init__(self):
        self.config = Config()
        self.parser = ProxyParser(self.config)
        self.checker = ProxyChecker(self.config)

    def run(self):
        raw_proxies = self.parser.fetch_raw_proxies()
        if not raw_proxies:
            logging.warning("Список прокси пуст. Завершение работы.")
            return

        logging.info("Запуск проверки в %d потоков...", self.config.MAX_WORKERS)
        valid_count = 0

        with open(self.config.OUTPUT_FILE, "w", encoding="utf-8") as file:
            with ThreadPoolExecutor(max_workers=self.config.MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self.checker.check_single_proxy, proxy): proxy 
                    for proxy in raw_proxies
                }
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        file.write(f"{result}\n")
                        file.flush()
                        valid_count += 1

        logging.info("Проверка завершена!")
        logging.info("Всего рабочих прокси найдено: %d", valid_count)
        logging.info("Результаты сохранены в файл: %s", self.config.OUTPUT_FILE)

if __name__ == "__main__":
    app = Application()
    app.run()

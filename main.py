import requests
import json
import logging
import time
import asyncio
import telegram
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import colorlog
from fake_useragent import UserAgent
import urllib3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from asyncio import Queue
import itertools
from colorama import Fore, Style, init
import base64
import os
import sys
import threading

# Nonaktifkan logging untuk telegram
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

CONFIG_FILE = "config.json"
PROXY_FILE = "proxies.txt"

log_colors = {
    'DEBUG': 'cyan',
    'INFO': 'white',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'SUCCESS': 'green'
}

formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    log_colors=log_colors
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')
        
def key_bot():
    url = base64.b64decode("aHR0cDovL2l0YmFhcnRzLmNvbS9hcGkuanNvbg==").decode('utf-8')
    try:
        response = requests.get(url)
        response.raise_for_status()
        try:
            data = response.json()
            header = data['header']
            print(header)
        except json.JSONDecodeError:
            print(response.text)
    except requests.RequestException as e:
        print(f"[⚔] | Failed to load header")
        
def log_success(message, *args, **kwargs):
    if logger.isEnabledFor(SUCCESS_LEVEL):
        logger._log(SUCCESS_LEVEL, message, args, **kwargs)

logging.success = log_success

def read_config(filename=CONFIG_FILE):
    try:
        with open(filename, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        logging.error(f"Configuration file '{filename}' not found.")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'.")
        return {}

def read_proxies(filename=PROXY_FILE):
    proxies = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                proxy = line.strip()
                if proxy:
                    proxies.append(proxy)
    except FileNotFoundError:
        logging.error(f"Proxy file '{filename}' not found.")
    return proxies

def parse_proxy(proxy):
    """Parse proxy string into format for requests."""
    proxy_url = urlparse(proxy)
    if proxy_url.scheme in ['http', 'https', 'socks5']:
        if proxy_url.username and proxy_url.password:
            return {
                'http': f"{proxy_url.scheme}://{proxy_url.username}:{proxy_url.password}@{proxy_url.hostname}:{proxy_url.port}",
                'https': f"{proxy_url.scheme}://{proxy_url.username}:{proxy_url.password}@{proxy_url.hostname}:{proxy_url.port}",
            }
        else:
            return {
                'http': f"{proxy_url.scheme}://{proxy_url.hostname}:{proxy_url.port}",
                'https': f"{proxy_url.scheme}://{proxy_url.hostname}:{proxy_url.port}",
            }
    return {}

def check_proxy(proxy):
    """Check if the proxy is active by sending a request to a test URL."""
    proxies = parse_proxy(proxy)
    test_url = "http://httpbin.org/ip"  
    try:
        response = requests.get(test_url, proxies=proxies, timeout=5)
        if response.status_code == 200:
            return True
    except requests.RequestException:
        return False

def get_active_proxies():
    """Check all proxies and return a list of active proxies using multithreading."""
    stop_loading = loading_animation()
    proxies = read_proxies(PROXY_FILE)
    active_proxies = []

    with ThreadPoolExecutor(max_workers=20) as executor: 
        futures = [executor.submit(check_proxy, proxy) for proxy in proxies]
        
        for future, proxy in zip(futures, proxies):
            if future.result():
                active_proxies.append(proxy)

    stop_loading()

    if active_proxies:
        logging.success(f"Found {len(active_proxies)} active proxies.")
        return active_proxies
    else:
        logging.error("No active proxies found.")
        return []

def update_proxies_file(active_proxies):
    """Update proxies.txt file with only active proxies."""
    with open(PROXY_FILE, 'w') as file:
        for proxy in active_proxies:
            file.write(f"{proxy}\n")
    logging.success(f"Updated {PROXY_FILE} with {len(active_proxies)} active proxies.")

def create_session(proxy=None):
    session = requests.Session()
    session.mount('http://', HTTPAdapter(pool_connections=10, pool_maxsize=10))
    session.mount('https://', HTTPAdapter(pool_connections=10, pool_maxsize=10))
    if proxy:
        proxies = parse_proxy(proxy)
        session.proxies.update(proxies)
    return session

config = read_config(CONFIG_FILE)
bot_token = config.get("telegram_bot_token")
chat_id = config.get("telegram_chat_id")
use_proxy = config.get("use_proxy", False)
use_telegram = config.get("use_telegram", False)
poll_interval = config.get("poll_interval", 120)  

if use_telegram and (not bot_token or not chat_id):
    logging.error("Missing 'bot_token' or 'chat_id' in 'config.json'.")
    exit(1)

bot = telegram.Bot(token=bot_token) if use_telegram else None
keepalive_url = "https://www.aeropres.in/chromeapi/dawn/v1/userreward/keepalive"
get_points_url = "https://www.aeropres.in/api/atom/v1/userreferral/getpoint"
extension_id = "fpdkjdnhkakefebpekbdhillbhonfjjp"
_v = "1.0.7"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ua = UserAgent()

def read_account(filename="config.json"):
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
            accounts = data.get("accounts", [])
            return accounts 
    except FileNotFoundError:
        logging.error(f"Config file '{filename}' not found.")
        return []
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in '{filename}'.")
        return []

def total_points(headers, session):
    try:
        response = session.get(get_points_url, headers=headers, verify=False)
        response.raise_for_status()

        json_response = response.json()
        if json_response.get("status"):
            reward_point_data = json_response["data"]["rewardPoint"]
            referral_point_data = json_response["data"]["referralPoint"]
            total_points = (
                reward_point_data.get("points", 0) +
                reward_point_data.get("registerpoints", 0) +
                reward_point_data.get("signinpoints", 0) +
                reward_point_data.get("twitter_x_id_points", 0) +
                reward_point_data.get("discordid_points", 0) +
                reward_point_data.get("telegramid_points", 0) +
                reward_point_data.get("bonus_points", 0) +
                referral_point_data.get("commission", 0)
            )
            return total_points
        else:
            logging.warning(f"Warning: {json_response.get('message', 'Unknown error when fetching points')}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching points: {e}")
    return 0

def keep_alive(headers, email, session):
    keepalive_payload = {
        "username": email,
        "extensionid": extension_id,
        "numberoftabs": 0,
        "_v": _v
    }

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[502, 503, 504]  # Bad Gateway termasuk di sini
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    try:
        response = session.post(
            keepalive_url, 
            headers=headers, 
            json=keepalive_payload,
            verify=False,
            timeout=10  # Tambahkan timeout
        )
        response.raise_for_status()

        json_response = response.json()
        if json_response.get('status') == True:  # Periksa status response
            return True, json_response.get('message', 'Success')
        else:
            return False, json_response.get('message', 'Failed')
            
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {str(e)}"

message_queue = Queue()

async def telegram_worker():
    while True:
        message = await message_queue.get()
        await telegram_message(message)
        message_queue.task_done()

async def queue_telegram_message(message):
    await message_queue.put(message)

async def telegram_message(message):
    if use_telegram:
        try:
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
            email = message.split('*')[1] if '*' in message else 'Unknown'
            print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} ║ Data {email} Successfully Sent")
            await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"Error sending Telegram message: {e}")

async def process_account(account, proxy_cycle, active_proxies):
    email = account["email"]
    token = account["token"]
    
    # Tambahkan validasi token
    if not token or len(token) < 10:  # Sesuaikan dengan panjang token yang valid
        logging.error(f"Invalid token for {email}")
        return

    headers = { 
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": ua.random,
        "Accept": "application/json",  # Tambahkan header Accept
        "Connection": "keep-alive"     # Tambahkan Connection header
    }

    all_failed = True 

    for _ in range(len(active_proxies)):
        proxy = next(proxy_cycle)
        session = create_session(proxy)

        success, status_message = keep_alive(headers, email, session)
        proxy_short = proxy.split('/')[-2]

        if success:
            points = total_points(headers, session)
            print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} ║ {email} | {points}p | {proxy_short}")
            
            message = (
                f"╔═══════════════════════\n"
                f"║ 🎯 *{email}*\n"
                f"╠═══════════════════════\n"
                f"║ 💎 Points   : {points}\n"
                f"║ 🔒 Proxy    : {proxy_short}\n" 
                f"║ ✅ Status   : Success\n"
                f"║ ⏰ Time     : {time.strftime('%H:%M:%S')}\n"
                f"║ 👨‍💻 By       : @UXScript\n"
                f"╚═══════════════════════"
            )
            await queue_telegram_message(message)
            all_failed = False
            break 
        else:
            error_msg = "Bad Gateway" if "Bad Gateway" in status_message else "Failed"
            print(f"{Fore.RED}[FAIL]{Style.RESET_ALL}    ║ {email} | {proxy_short} | {error_msg}")
    
    if all_failed:
        pass

def clear_line():
    """Membersihkan baris saat ini"""
    sys.stdout.write('\r' + ' ' * 80 + '\r')
    sys.stdout.flush()

def loading_animation():
    chars = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    stop_animation = False
    
    def animate():
        i = 0
        while not stop_animation:
            sys.stdout.write('\r' + f'Loading {chars[i % len(chars)]}')
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
        clear_line()  # Bersihkan baris loading
    
    thread = threading.Thread(target=animate)
    thread.daemon = True
    thread.start()
    
    def stop():
        nonlocal stop_animation
        stop_animation = True
        thread.join()  # Tunggu thread selesai
        clear_line()  # Pastikan baris benar-benar bersih
    
    return stop

async def main():
    clear_terminal()
    
    # Loading saat memulai program
    stop_loading = loading_animation()
    await asyncio.sleep(1)
    stop_loading()
    
    # Loading saat memeriksa konfigurasi
    stop_loading = loading_animation()
    await asyncio.sleep(1)
    stop_loading()
    key_bot()
    accounts = read_account()
    
    # Loading saat memeriksa proxy
    active_proxies = get_active_proxies()
    
    # Loading saat memperbarui file proxy
    stop_loading = loading_animation()
    await asyncio.sleep(1)
    stop_loading()
    update_proxies_file(active_proxies)
    
    # Loading saat mempersiapkan koneksi
    stop_loading = loading_animation()
    await asyncio.sleep(2)
    stop_loading()
    proxy_cycle = itertools.cycle(active_proxies)
    asyncio.create_task(telegram_worker())
    
    print(f"\n{Fore.CYAN}[INFO]{Style.RESET_ALL} Program ready to run!")
    await asyncio.sleep(1)

    while True:
        for account in accounts:
            await process_account(account, proxy_cycle, active_proxies)  
        logging.info(f"Waiting {poll_interval} seconds before next cycle.")
        await asyncio.sleep(poll_interval)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")

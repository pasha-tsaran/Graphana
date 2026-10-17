"""Continuous cryptocurrency backend simulation, based on local-emulate.md."""

import argparse
import random
import signal
import threading

import requests

from loki_client import send_log_to_loki


class CryptoBackend:
    def __init__(self):
        self.prices = dict(BTC=45000, ETH=3200, BNB=320, ADA=0.45,
                           SOL=95, DOT=6.5, MATIC=0.85, AVAX=25)
        self.users = ["crypto_trader_1", "hodler_2024", "defi_master",
                      "nft_collector", "mining_pool"]
        self.transaction_id = 0

    def trading_event(self):
        for symbol in self.prices:
            self.prices[symbol] = round(self.prices[symbol] * random.uniform(0.95, 1.05), 4)
        self.transaction_id += 1
        user = random.choice(self.users)
        symbol = random.choice(list(self.prices))
        operation = random.choice(["buy", "sell", "transfer"])
        status = random.choice(["completed", "pending", "failed"])
        amount = round(random.uniform(0.001, 10), 6)
        level = {"completed": "INFO", "pending": "WARNING", "failed": "ERROR"}[status]
        return (f"Транзакция #{self.transaction_id}: {user} {operation} {amount} "
                f"{symbol}, цена ${self.prices[symbol]}, статус {status}", "trading", level)

    def user_event(self):
        action = random.choice(["вошёл в систему", "проверил баланс", "просмотрел портфель",
                                "настроил уведомления", "запросил историю транзакций"])
        return f"Пользователь {random.choice(self.users)} {action}", "user_activity", "INFO"

    def system_event(self):
        action = random.choice(["Проверка кошельков", "Синхронизация с блокчейном",
                                "Обновление курсов", "Резервное копирование",
                                "Проверка лимитов транзакций"])
        return f"Система: {action}", "system", random.choice(["INFO", "DEBUG", "WARNING"])

    def next_event(self):
        return random.choice([self.trading_event, self.user_event, self.system_event])()


def deliver(event):
    message, job, level = event
    try:
        send_log_to_loki(message, job, level)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"Loki delivery failed: {exc}", flush=True)
        return False
    print(f"Sent [{level}] [{job}] {message}", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Send a batch and exit")
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    backend = CryptoBackend()
    if args.once:
        events = [(f"Демонстрационное событие {level}", "system", level)
                  for level in ("INFO", "DEBUG", "WARNING", "ERROR")]
        events.extend(backend.next_event() for _ in range(max(0, args.count - 4)))
        results = [deliver(event) for event in events[:args.count]]
        return 0 if all(results) else 1

    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    deliver(("Криптовалютный бэкэнд запущен (учебная эмуляция)", "system", "INFO"))
    while not stopped.is_set():
        deliver(backend.next_event())
        stopped.wait(random.uniform(2, 8))
    deliver(("Криптовалютный бэкэнд остановлен", "system", "INFO"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

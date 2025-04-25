from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from web3 import Web3
from loguru import logger
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Основной URL API BeraScan
BERASCAN_API_URL = "https://api.berascan.com/api"
GAME_CONTRACT = "0x5487cB78417Aa5923b80cdCf046a6554CA395874"
BERASCAN_API_KEY = os.getenv("BERASCAN_API_KEY")

if not BERASCAN_API_KEY:
    raise ValueError("BERASCAN_API_KEY не найден в переменных окружения. Пожалуйста, создайте файл .env с BERASCAN_API_KEY=ваш_ключ")

@dataclass
class Transaction:
    hash: str
    from_address: str
    to_address: str
    value: float
    timestamp: datetime
    method: str
    input_data: str

class BeraScanAnalyzer:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_transactions(self, address: str, start_block: int = 0, page: int = 1, offset: int = 1000) -> List[Transaction]:
        """Получение транзакций через BeraScan API"""
        if not self.session:
            raise RuntimeError("Session not initialized")
            
        try:
            params = {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": start_block,
                "endblock": 99999999,
                "page": page,
                "offset": offset,
                "sort": "asc",
                "apikey": BERASCAN_API_KEY
            }
            
            # Получаем транзакции для адреса
            async with self.session.get(BERASCAN_API_URL, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ошибка API (статус {response.status}): {error_text}")
                    return []
                    
                data = await response.json()
                if data.get('status') != '1':
                    logger.error(f"Ошибка API: {data.get('message', 'Неизвестная ошибка')}")
                    return []
                    
                transactions = []
                
                for tx in data.get('result', []):
                    try:
                        transaction = Transaction(
                            hash=tx['hash'],
                            from_address=tx['from'],
                            to_address=tx['to'],
                            value=float(tx['value']) / 1e18,  # Конвертируем из wei в ETH
                            timestamp=datetime.fromtimestamp(int(tx['timeStamp'])),
                            method=tx.get('methodId', ''),
                            input_data=tx.get('input', '')
                        )
                        transactions.append(transaction)
                    except Exception as e:
                        logger.error(f"Ошибка при обработке транзакции {tx.get('hash')}: {e}")
                        
                return transactions
                
        except Exception as e:
            logger.error(f"Ошибка при получении транзакций: {e}")
            return []
            
    def analyze_spending(self, transactions: List[Transaction]) -> Dict:
        """Анализ расходов на спавн"""
        total_spent = 0.0
        spawn_transactions = []
        
        for tx in transactions:
            # Проверяем, что транзакция направлена в контракт игры
            if tx.to_address.lower() == GAME_CONTRACT.lower():
                total_spent += tx.value
                spawn_transactions.append(tx)
                
        return {
            'total_spent': total_spent,
            'transaction_count': len(spawn_transactions),
            'transactions': spawn_transactions
        }

async def main():
    # Адрес кошелька для анализа
    wallet_address = "0x7301F25a31B80Ea80F3C03674d7B77B82aeC1e70"
    
    async with BeraScanAnalyzer() as analyzer:
        logger.info(f"Начинаем анализ транзакций для адреса {wallet_address}")
        
        # Получаем все транзакции (с пагинацией)
        all_transactions = []
        page = 1
        while True:
            transactions = await analyzer.get_transactions(wallet_address, page=page, offset=100)
            if not transactions:
                break
            all_transactions.extend(transactions)
            page += 1
            
            # Ограничение на количество запросов
            if page > 100:  # Максимум 10000 транзакций (100 страниц по 100 транзакций)
                break
        
        # Анализируем расходы
        analysis = analyzer.analyze_spending(all_transactions)
        
        # Выводим результаты
        logger.info("\nРезультаты анализа:")
        logger.info(f"Всего потрачено на спавн: {analysis['total_spent']:.4f} ETH")
        logger.info(f"Количество транзакций спавна: {analysis['transaction_count']}")
        
        logger.info("\nПоследние транзакции:")
        for tx in analysis['transactions'][-5:]:  # Показываем последние 5 транзакций
            logger.info(f"\nХеш: {tx.hash}")
            logger.info(f"Дата: {tx.timestamp}")
            logger.info(f"Сумма: {tx.value:.4f} ETH")
            logger.info(f"Метод: {tx.method}")

if __name__ == "__main__":
    asyncio.run(main())

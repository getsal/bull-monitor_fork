import streamlit as st
import asyncio
from datetime import datetime
import json
from web3 import Web3
import time
from loguru import logger
from collections import defaultdict
import pandas as pd

# Конфигурация
CONTRACT_ADDRESS = "0x784bb8fA1Db3413A1E98250fdce9Ddb7Eaf4BB0d"
BERACHAIN_RPC = "https://rpc.berachain.com"
QUEUE_SIZE = 300  # Максимальный размер очереди

# ABI для функции GetQueue
CONTRACT_ABI = [
    {
        "inputs": [],
        "name": "getQueue",
        "outputs": [
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "tokenId",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint256",
                        "name": "power",
                        "type": "uint256"
                    },
                    {
                        "internalType": "address",
                        "name": "account",
                        "type": "address"
                    },
                    {
                        "internalType": "string",
                        "name": "message",
                        "type": "string"
                    }
                ],
                "internalType": "struct QueuePlugin.Click[]",
                "name": "",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

class QueueMonitor:
    def __init__(self):
        try:
            self.w3 = Web3(Web3.HTTPProvider(BERACHAIN_RPC))
            if not self.w3.is_connected():
                raise ConnectionError("Не удалось подключиться к BeraChain RPC")
            
            # Проверяем адрес контракта
            if not self.w3.is_address(CONTRACT_ADDRESS):
                raise ValueError(f"Некорректный адрес контракта: {CONTRACT_ADDRESS}")
            
            self.contract = self.w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
            
            # Проверяем, что контракт существует
            code = self.w3.eth.get_code(CONTRACT_ADDRESS)
            if not code:
                raise ValueError(f"Контракт не существует по адресу: {CONTRACT_ADDRESS}")
                
            logger.info("Успешное подключение к BeraChain")
            logger.info(f"Адрес контракта: {CONTRACT_ADDRESS}")
            logger.info(f"Размер кода контракта: {len(code)} байт")
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации: {e}")
            raise
            
    async def get_queue_data(self):
        try:
            # Получаем текущий блок
            current_block = self.w3.eth.block_number
            logger.info(f"Текущий блок: {current_block}")
            
            # Пробуем получить данные
            queue = self.contract.functions.getQueue().call()
            return queue
        except Exception as e:
            logger.error(f"Ошибка при получении данных очереди: {str(e)}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            return []
            
    def analyze_queue(self, queue_data):
        if not queue_data:
            return {
                'total_entries': 0,
                'total_power': 0,
                'average_queue_power': 0,
                'wallet_stats': {},
                'nft_stats': {}
            }
            
        wallet_stats = defaultdict(lambda: {'count': 0, 'total_power': 0})
        nft_stats = defaultdict(lambda: {'count': 0, 'total_power': 0})
        total_power = 0
        
        for entry in queue_data:
            nft_id = entry[0]  # tokenId
            power = float(entry[1]) / 1e18  # power
            wallet = entry[2]  # account
            
            total_power += power
            wallet_stats[wallet]['count'] += 1
            wallet_stats[wallet]['total_power'] += power
            
            nft_stats[nft_id]['count'] += 1
            nft_stats[nft_id]['total_power'] += power
        
        # Сортируем статистику по количеству записей
        sorted_wallet_stats = dict(sorted(
            wallet_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        ))
        
        sorted_nft_stats = dict(sorted(
            nft_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        ))
        
        return {
            'total_entries': len(queue_data),
            'total_power': total_power,
            'average_queue_power': total_power / QUEUE_SIZE,
            'wallet_stats': sorted_wallet_stats,
            'nft_stats': sorted_nft_stats
        }

def main():
    st.title("Аналитика очереди GetQueue")
    st.write(f"Контракт: {CONTRACT_ADDRESS}")
    
    try:
        monitor = QueueMonitor()
        
        # Создаем контейнер для обновления данных
        queue_container = st.empty()
        
        while True:
            try:
                # Получаем данные очереди
                queue_data = asyncio.run(monitor.get_queue_data())
                
                # Анализируем данные
                analysis = monitor.analyze_queue(queue_data)
                
                # Отображаем аналитику
                with queue_container.container():
                    st.subheader("Общая статистика")
                    st.write(f"Всего записей в очереди: {analysis['total_entries']}")
                    st.write(f"Общая сила очереди: {analysis['total_power']:.2f} Spank Power")
                    st.write(f"Средняя сила очереди: {analysis['average_queue_power']:.2f} Spank Power")
                    
                    # Создаем DataFrame для статистики по кошелькам
                    wallet_data = []
                    for wallet, stats in analysis['wallet_stats'].items():
                        avg_power = stats['total_power'] / stats['count'] if stats['count'] > 0 else 0
                        wallet_data.append({
                            'Кошелек': wallet,
                            'Количество записей': stats['count'],
                            'Средняя сила (Spank Power)': f"{avg_power:.2f}"
                        })
                    
                    if wallet_data:
                        st.subheader("Статистика по кошелькам")
                        df_wallets = pd.DataFrame(wallet_data)
                        st.dataframe(df_wallets, use_container_width=True)
                    
                    # Создаем DataFrame для статистики по NFT
                    nft_data = []
                    for nft_id, stats in analysis['nft_stats'].items():
                        avg_power = stats['total_power'] / stats['count'] if stats['count'] > 0 else 0
                        nft_data.append({
                            'NFT ID': nft_id,
                            'Количество записей': stats['count'],
                            'Средняя сила (Spank Power)': f"{avg_power:.2f}"
                        })
                    
                    if nft_data:
                        st.subheader("Статистика по NFT")
                        df_nfts = pd.DataFrame(nft_data)
                        st.dataframe(df_nfts, use_container_width=True)
                
                # Обновляем каждые 10 секунд
                time.sleep(10)
                
            except Exception as e:
                st.error(f"Произошла ошибка при обновлении данных: {e}")
                time.sleep(5)
                
    except Exception as e:
        st.error(f"Критическая ошибка: {e}")
        st.stop()

if __name__ == "__main__":
    main()
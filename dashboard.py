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

def format_positions(positions):
    if not positions:
        return ""
    positions = sorted(positions)
    ranges = []
    start = positions[0]
    prev = positions[0]
    
    for pos in positions[1:]:
        if pos != prev + 1:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = pos
        prev = pos
    
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")
    
    return ", ".join(ranges)

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
                'live_queue': []
            }
            
        wallet_stats = defaultdict(lambda: {'count': 0, 'total_power': 0, 'nft_id': None, 'positions': []})
        total_power = 0
        
        # Анализ живой очереди
        live_queue = []
        current_wallet = None
        current_entry = None
        current_positions = []
        
        for i, entry in enumerate(queue_data):
            nft_id = entry[0]  # tokenId
            power = float(entry[1]) / 1e18  # power
            wallet = entry[2]  # account
            position = i + 1
            
            total_power += power
            
            # Обновляем статистику
            if not wallet_stats[wallet]['nft_id']:
                wallet_stats[wallet]['nft_id'] = nft_id
            wallet_stats[wallet]['count'] += 1
            wallet_stats[wallet]['total_power'] += power
            wallet_stats[wallet]['positions'].append(position)
            
            # Обработка живой очереди
            if wallet != current_wallet:
                if current_entry:
                    current_entry['Positions'] = format_positions(current_positions)
                    live_queue.append(current_entry)
                current_wallet = wallet
                current_positions = [position]
                current_entry = {
                    'Positions': str(position),
                    'Wallet': wallet,
                    'NFT ID': str(nft_id),
                    'Power': f"{power:.2f} SP"
                }
            else:
                current_positions.append(position)
                current_entry['Power'] = f"{float(current_entry['Power'].split()[0]) + power:.2f} SP"
        
        if current_entry:
            current_entry['Positions'] = format_positions(current_positions)
            live_queue.append(current_entry)
        
        # Сортируем статистику по количеству записей
        sorted_wallet_stats = dict(sorted(
            wallet_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        ))
        
        return {
            'total_entries': len(queue_data),
            'total_power': total_power,
            'average_queue_power': total_power / QUEUE_SIZE,
            'wallet_stats': sorted_wallet_stats,
            'live_queue': live_queue
        }

def main():
    st.title("Bullas breadline analytics by Klimmo")
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
                    st.subheader("General stats")
                    st.write(f"Total spank power: {analysis['total_power']:.2f} SP")
                    st.write(f"Average: {analysis['average_queue_power']:.2f} SP")
                    st.write(f"Unique wallets: {len(analysis['wallet_stats'])}")
                    
                    # Отображаем живую очередь
                    if analysis['live_queue']:
                        st.subheader("Live Queue")
                        df_live = pd.DataFrame(analysis['live_queue'])
                        st.dataframe(df_live, use_container_width=True, hide_index=True)
                    
                    # Создаем объединенную таблицу статистики
                    stats_data = []
                    for wallet, stats in analysis['wallet_stats'].items():
                        avg_power = stats['total_power'] / stats['count'] if stats['count'] > 0 else 0
                        stats_data.append({
                            'Wallet': wallet,
                            'Positions': format_positions(stats['positions']),
                            'NFT ID': stats['nft_id'],
                            'Count': stats['count'],
                            'SP': f"{avg_power:.2f}"
                        })
                    
                    if stats_data:
                        st.subheader("Wallet stats")
                        df_stats = pd.DataFrame(stats_data)
                        st.dataframe(df_stats, use_container_width=True, hide_index=True)
                
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

import streamlit as st
import asyncio
from datetime import datetime
import json
from web3 import Web3
import time
from loguru import logger
from collections import defaultdict
import pandas as pd
import requests
from heatmap import HeatmapAnalyzer
from gamepass_analyzer import GamePassAnalyzer

# Configuration
CONTRACT_ADDRESS = "0x784bb8fA1Db3413A1E98250fdce9Ddb7Eaf4BB0d"
BERACHAIN_RPC = "https://rpc.berachain.com"
QUEUE_SIZE = 300  # Maximum queue size

# Contract for heatmap analysis
HEATMAP_CONTRACT = "0x5487cb78417aa5923b80cdcf046a6554ca395874"
API_KEY = "AVBDTC7X9DGP6IQK5RD8I6IK2666X1SPWF"

# ABI for GetQueue function
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

def test_api_directly():
    """Direct API testing"""
    try:
        logger.info("Testing BeraChain API...")
        url = "https://api.berascan.com/api"
        params = {
            "module": "account",
            "action": "txlist",
            "address": HEATMAP_CONTRACT,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 10,
            "sort": "desc",
            "apikey": API_KEY
        }
        
        logger.info(f"Direct API request: {url}")
        logger.info(f"Parameters: {params}")
        
        response = requests.get(url, params=params)
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API response: {data}")
            return True
        else:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error testing API: {e}")
        return False

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
                raise ConnectionError("Failed to connect to BeraChain RPC")
            
            # Check contract address
            if not self.w3.is_address(CONTRACT_ADDRESS):
                raise ValueError(f"Invalid contract address: {CONTRACT_ADDRESS}")
            
            self.contract = self.w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
            
            # Check if contract exists
            code = self.w3.eth.get_code(CONTRACT_ADDRESS)
            if not code:
                raise ValueError(f"Contract does not exist at address: {CONTRACT_ADDRESS}")
                
            logger.info("Successfully connected to BeraChain")
            logger.info(f"Contract address: {CONTRACT_ADDRESS}")
            logger.info(f"Contract code size: {len(code)} bytes")
            
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            raise
            
    async def get_queue_data(self):
        try:
            # Get current block
            current_block = self.w3.eth.block_number
            logger.info(f"Current block: {current_block}")
            
            # Try to get data
            queue = self.contract.functions.getQueue().call()
            return queue
        except Exception as e:
            logger.error(f"Error getting queue data: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
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
        
        # Live queue analysis
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
            
            # Update statistics
            if not wallet_stats[wallet]['nft_id']:
                wallet_stats[wallet]['nft_id'] = nft_id
            wallet_stats[wallet]['count'] += 1
            wallet_stats[wallet]['total_power'] += power
            wallet_stats[wallet]['positions'].append(position)
            
            # Live queue processing
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
        
        # Sort wallet stats by entry count
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

def display_queue_data(monitor):
    """Function to display queue data"""
    # Get queue data
    queue_data = asyncio.run(monitor.get_queue_data())
    analysis = monitor.analyze_queue(queue_data)
    
    st.subheader("General Statistics")
    st.write(f"Total spank power: {analysis['total_power']:.2f} SP")
    st.write(f"Average: {analysis['average_queue_power']:.2f} SP")
    st.write(f"Unique wallets: {len(analysis['wallet_stats'])}")
    
    if analysis['live_queue']:
        st.subheader("Live Queue")
        df_live = pd.DataFrame(analysis['live_queue'])
        st.dataframe(df_live, use_container_width=True, hide_index=True)
    
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
        st.subheader("Wallet Statistics")
        df_stats = pd.DataFrame(stats_data)
        st.dataframe(df_stats, use_container_width=True, hide_index=True)

def display_heatmap_data(heatmap_analyzer):
    """Function to display heatmap"""
    st.subheader("Activity Analysis")
    
    # Test API directly
    api_status = test_api_directly()
    if not api_status:
        st.error("Error accessing Berascan API. Check logs for detailed information.")
        st.info("Try again later or check Berascan API availability.")
        return
    
    # Force data update on page load
    with st.spinner('Loading heatmap data...'):
        # Show optimal time
        heatmap_analyzer.find_optimal_time()
        
        # Show heatmap
        heatmap_analyzer.plot_heatmap()
        
    # Add manual refresh button
    if st.button("Refresh Heatmap Data"):
        st.rerun()

def display_gamepass_analytics(gamepass_analyzer):
    """Function to display GamePass analytics"""
    try:
        gamepass_analyzer.display_gamepass_analytics()
    except Exception as e:
        logger.error(f"Critical error in GamePass Analytics: {e}")
        st.error("Failed to load GamePass Analytics")
        st.info("The GamePass Analytics module encountered an error with the blockchain API. This is likely due to RPC limitations or contract issues.")
        st.warning("The log shows: 'Error executing multicall for batch: execution reverted: revert: Multicall3: call failed'")
        
        # Show technical details in expander
        with st.expander("Technical Details"):
            st.write("The error is occurring because the multicall contract is failing to execute batch calls to retrieve UPS data.")
            st.write("This could be due to:")
            st.write("1. Contract function restrictions")
            st.write("2. RPC provider limitations")
            st.write("3. Blockchain network congestion")
            st.write("4. Contract state that prevents certain operations")
            st.code("Check console logs for detailed error information", language="bash")

def main():
    st.title("Bullas Breadline Analytics")
    st.write(f"Contract: {CONTRACT_ADDRESS}")
    
    try:
        # Test API directly before initialization
        api_works = test_api_directly()
        if not api_works:
            st.warning("Warning: Berascan API is not responding correctly. Heatmap functionality may be limited.")
        
        # Initialize components
        monitor = QueueMonitor()
        heatmap_analyzer = HeatmapAnalyzer()
        gamepass_analyzer = GamePassAnalyzer()
        
        # Create tabs
        tab1, tab2, tab3 = st.tabs(["Queue", "Heatmap", "GamePass Analytics"])
        
        # Display data based on selected tab
        with tab1:
            display_queue_data(monitor)
        
        with tab2:
            display_heatmap_data(heatmap_analyzer)
            
        with tab3:
            display_gamepass_analytics(gamepass_analyzer)
            
        # Add auto-refresh for active tab (except for GamePass tab which has its own refresh mechanism)
        if st.session_state.get('active_tab') != 'GamePass Analytics':
            time.sleep(10)
            st.rerun()
                
    except Exception as e:
        st.error(f"Critical error: {e}")
        logger.error(f"Critical error: {e}")
        st.stop()

if __name__ == "__main__":
    main()
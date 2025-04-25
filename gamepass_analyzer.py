import logging
import time
from collections import defaultdict
from web3 import Web3
from typing import Dict, List, Tuple
import pandas as pd
import streamlit as st
from loguru import logger
from tqdm import tqdm
import random

# Web3 configuration
BERACHAIN_RPC = "https://orbital-little-dream.bera-mainnet.quiknode.pro/ecd6f68a9cb932ead65eca4f1902228c7366b025/"
CONTRACT_ADDRESS = "0x0dB74D6326623eFae36d2456c7830BF38B444389"  # Main contract
NFT_CONTRACT_ADDRESS = "0x333814f5E16EEE61d0c0B03a5b6ABbD424B381c2"  # NFT contract
MULTICALL_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"  # Multicall contract

# ABI for Multicall contract
MULTICALL_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {
                        "internalType": "address",
                        "name": "target",
                        "type": "address"
                    },
                    {
                        "internalType": "bytes",
                        "name": "callData",
                        "type": "bytes"
                    }
                ],
                "internalType": "struct Multicall3.Call[]",
                "name": "calls",
                "type": "tuple[]"
            }
        ],
        "name": "aggregate",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "blockNumber",
                "type": "uint256"
            },
            {
                "internalType": "bytes[]",
                "name": "returnData",
                "type": "bytes[]"
            }
        ],
        "stateMutability": "payable",
        "type": "function"
    }
]

# ABI for NFT contract (only ownerOf function)
NFT_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ABI for main contract (only tokenId_Ups function)
MAIN_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "_tokenId", "type": "uint256"}],
        "name": "tokenId_Ups",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class GamePassAnalyzer:
    def __init__(self):
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(BERACHAIN_RPC))
        
        # Create contract instances
        self.multicall_contract = self.w3.eth.contract(address=MULTICALL_ADDRESS, abi=MULTICALL_ABI)
        self.nft_contract = self.w3.eth.contract(address=NFT_CONTRACT_ADDRESS, abi=NFT_ABI)
        self.main_contract = self.w3.eth.contract(address=CONTRACT_ADDRESS, abi=MAIN_ABI)
        
        # Инициализация кеша из session_state, если доступен
        if 'cached_ups_data' not in st.session_state:
            st.session_state['cached_ups_data'] = None
        if 'cached_owners_data' not in st.session_state:
            st.session_state['cached_owners_data'] = None
        if 'cached_last_update' not in st.session_state:
            st.session_state['cached_last_update'] = None
            
        # Локальный кеш из session_state
        self._cached_ups_data = st.session_state['cached_ups_data']
        self._cached_owners_data = st.session_state['cached_owners_data'] 
        self._last_update = st.session_state['cached_last_update']
        
        logger.info(f"GamePassAnalyzer initialized with contract: {CONTRACT_ADDRESS}")
    
    def format_token(self, value: int) -> str:
        """Format token value to human-readable form"""
        try:
            val = float(value) / 1e18
            if val >= 1000:
                return f"{val/1000:.2f}K"
            return f"{val:.2f}"
        except:
            return "0.00"
    
    def get_ups_for_token_range(self, start_id: int, end_id: int, batch_size: int = 6969) -> Dict[int, int]:
        """
        Get UPS for a range of tokens using one large multicall.
        
        Args:
            start_id: Start token ID
            end_id: End token ID
            batch_size: Batch size for multicall (default: 6969 for all tokens at once)
            
        Returns:
            dict: Dictionary {token_id: ups}
        """
        results = {}
        
        # Create token range
        token_range = list(range(start_id, end_id + 1))
        logger.info(f"Getting UPS for all {len(token_range)} tokens at once")
        
        # Initialize results with zeros
        for token_id in token_range:
            results[token_id] = 0
        
        try:
            # Prepare data for multicall - all tokens at once
            calls = []
            for token_id in token_range:
                ups_call_data = self.main_contract.encodeABI(
                    fn_name="tokenId_Ups",
                    args=[token_id]
                )
                calls.append({
                    "target": CONTRACT_ADDRESS,
                    "callData": ups_call_data
                })
            
            # Execute multicall for all tokens
            logger.info(f"Executing multicall for all {len(token_range)} tokens...")
            
            # This might take some time
            multicall_result = self.multicall_contract.functions.aggregate(calls).call()
            _, return_data = multicall_result
            
            # Process results
            active_count = 0
            
            for i, result in enumerate(return_data):
                token_id = token_range[i]
                try:
                    # Decode UPS value
                    ups = int.from_bytes(result, byteorder='big')
                    results[token_id] = ups
                    if ups > 0:
                        active_count += 1
                except Exception as e:
                    logger.error(f"Error decoding UPS for token_id={token_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error executing multicall for all tokens: {e}")
        
        # Filter results to only include tokens with UPS > 0
        active_tokens = {t: u for t, u in results.items() if u > 0}
        logger.info(f"Found {len(active_tokens)} active tokens with UPS > 0")
        
        return active_tokens
            
    def get_owners_for_tokens(self, token_ids: List[int], batch_size: int = 6969) -> Dict[int, str]:
        """
        Get owners for a list of tokens using one large multicall.
        
        Args:
            token_ids: List of token IDs
            batch_size: Batch size for multicall (default: 6969 for all tokens at once)
            
        Returns:
            dict: Dictionary {token_id: owner_address}
        """
        if not token_ids:
            logger.warning("No tokens provided to get owners for")
            return {}
            
        results = {}
        
        # Create empty result for error cases
        for token_id in token_ids:
            results[token_id] = None
        
        try:
            # Prepare data for multicall - all tokens at once
            calls = []
            for token_id in token_ids:
                owner_call_data = self.nft_contract.encodeABI(
                    fn_name="ownerOf",
                    args=[token_id]
                )
                calls.append({
                    "target": NFT_CONTRACT_ADDRESS,
                    "callData": owner_call_data
                })
            
            # Execute multicall for all tokens
            logger.info(f"Executing multicall for all {len(token_ids)} token owners...")
            
            # This might take some time
            multicall_result = self.multicall_contract.functions.aggregate(calls).call()
            _, return_data = multicall_result
            
            # Process results
            for i, result in enumerate(return_data):
                token_id = token_ids[i]
                try:
                    # Decode address from bytes
                    owner = Web3.to_checksum_address('0x' + result.hex()[-40:])
                    results[token_id] = owner
                except Exception as e:
                    logger.error(f"Error decoding owner for token_id={token_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error executing multicall for all token owners: {e}")
                
        return results
    
    def get_wallet_rankings(self, ups_data: Dict[int, int], owner_data: Dict[int, str]) -> Dict:
        """
        Calculate wallet rankings based on UPS data and ownership data.
        
        Args:
            ups_data: Dictionary {token_id: ups}
            owner_data: Dictionary {token_id: owner_address}
            
        Returns:
            dict: Dictionary with wallet rankings information
        """
        # Ensure we have owner_data, even if empty
        if owner_data is None:
            logger.warning("No owner data available for wallet rankings")
            owner_data = {}
            
        # Group tokens by wallets and calculate total UPS
        wallet_ups = defaultdict(int)
        wallet_tokens = defaultdict(list)
        
        for token_id, owner in owner_data.items():
            if owner and token_id in ups_data:
                wallet_ups[owner] += ups_data[token_id]
                wallet_tokens[owner].append(token_id)
        
        # Sort wallets by total UPS
        sorted_wallets = sorted(wallet_ups.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'wallet_ups': wallet_ups,
            'wallet_tokens': wallet_tokens,
            'sorted_wallets': sorted_wallets
        }
    
    def _save_to_cache(self, ups_data, owner_data, timestamp):
        """Сохраняет данные в кеш и session_state"""
        self._cached_ups_data = ups_data
        self._cached_owners_data = owner_data
        self._last_update = timestamp
        
        # Сохраняем также в session_state
        st.session_state['cached_ups_data'] = ups_data
        st.session_state['cached_owners_data'] = owner_data
        st.session_state['cached_last_update'] = timestamp
        
        logger.info(f"Data cached at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}")
        
    def get_gamepass_data(self, force_refresh: bool = False) -> Dict:
        """
        Get GamePass data with caching support.
        
        Args:
            force_refresh: Force refresh data even if cache is fresh
            
        Returns:
            dict: Dictionary with GamePass data
        """
        current_time = time.time()
        
        # Initialize the session state for last refresh time if not exists
        if 'last_gamepass_refresh_time' not in st.session_state:
            st.session_state['last_gamepass_refresh_time'] = 0
        
        # Создаем тестовые данные если вообще ничего нет и никогда не было
        if (self._cached_ups_data is None and st.session_state['cached_ups_data'] is None):
            # Загружаем данные из session_state если они там есть
            if st.session_state['cached_ups_data'] is not None:
                self._cached_ups_data = st.session_state['cached_ups_data']
                self._cached_owners_data = st.session_state['cached_owners_data']
                self._last_update = st.session_state['cached_last_update']
                logger.info("Loaded cache from session_state")
        
        # Проверяем, есть ли кешированные данные (в локальных переменных или session_state)
        has_cached_data = False
        
        # Проверка локального кеша
        if self._cached_ups_data is not None and len(self._cached_ups_data) > 0:
            has_cached_data = True
        # Проверка кеша в session_state как резервный вариант
        elif st.session_state['cached_ups_data'] is not None and len(st.session_state['cached_ups_data']) > 0:
            self._cached_ups_data = st.session_state['cached_ups_data']
            self._cached_owners_data = st.session_state['cached_owners_data']
            self._last_update = st.session_state['cached_last_update']
            has_cached_data = True
            logger.info("Restored cache from session_state")
        
        # Check if time to refresh (1 minute passed)
        time_since_refresh = current_time - st.session_state['last_gamepass_refresh_time']
        should_refresh = time_since_refresh >= 60 or force_refresh
        
        # Check if cache exists and is fresh
        if not should_refresh and has_cached_data:
            logger.info(f"Using cached data from {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_update))}")
            return {
                'ups_data': self._cached_ups_data,
                'owner_data': self._cached_owners_data or {},  # Ensure we return at least an empty dict
                'last_update': self._last_update
            }
        
        # If we're forcing a refresh or the minute has passed, update the timestamp
        if should_refresh:
            st.session_state['last_gamepass_refresh_time'] = current_time
            logger.info(f"Refreshing GamePass data after {time_since_refresh:.1f} seconds")
            
            # Fetch new data
            logger.info("Fetching fresh GamePass data for all 6969 tokens using multicall")
            
            try:
                # Get UPS data for all tokens (0-6968) in one request
                new_ups_data = self.get_ups_for_token_range(0, 6968, 6969)
                
                # Initialize owner_data to empty dict
                new_owner_data = {}
                
                # AFTER getting UPS data, try to get owner data in a separate try block
                if new_ups_data and len(new_ups_data) > 0:
                    active_tokens = list(new_ups_data.keys())
                    
                    try:
                        new_owner_data = self.get_owners_for_tokens(active_tokens, 6969)
                    except Exception as e:
                        logger.error(f"Failed to get owner data: {e}")
                        # Используем кешированные данные владельцев, если они есть
                        if self._cached_owners_data:
                            new_owner_data = self._cached_owners_data
                            logger.info("Using cached owner data due to error")
                else:
                    logger.warning("No active tokens found with UPS > 0 in new data")
                
                # Проверяем, что новые данные не пустые
                if new_ups_data and len(new_ups_data) > 0:
                    # Сохраняем новые данные в кеш
                    self._save_to_cache(new_ups_data, new_owner_data, current_time)
                    
                    logger.info(f"Returning fresh data with {len(new_ups_data)} active tokens")
                    return {
                        'ups_data': new_ups_data,
                        'owner_data': new_owner_data,
                        'last_update': current_time
                    }
                else:
                    logger.warning("Received empty new data")
                    
                    # Если новые данные пустые, но у нас есть кеш, используем его
                    if has_cached_data:
                        logger.info("New data is empty, using cached data instead")
                        return {
                            'ups_data': self._cached_ups_data,
                            'owner_data': self._cached_owners_data or {},
                            'last_update': self._last_update
                        }
                    else:
                        # Если и новые данные пустые, и кеша нет
                        logger.error("No data available at all")
                        return {
                            'ups_data': {},
                            'owner_data': {},
                            'last_update': current_time
                        }
            
            except Exception as e:
                logger.error(f"Error getting GamePass data: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                
                # Если у нас есть кешированные данные, используем их при ошибке
                if has_cached_data:
                    logger.info("Using cached data due to error")
                    return {
                        'ups_data': self._cached_ups_data,
                        'owner_data': self._cached_owners_data or {},
                        'last_update': self._last_update
                    }
                
                # Если нет кешированных данных
                logger.error("No cached data available to use as fallback")
                return {
                    'ups_data': {},
                    'owner_data': {},
                    'last_update': current_time
                }
        else:
            # If we already have cached data and it's not time to refresh yet
            logger.info("Not time to refresh yet, using cached data")
            return {
                'ups_data': self._cached_ups_data,
                'owner_data': self._cached_owners_data or {},
                'last_update': self._last_update
            }
    
    def analyze_gamepass_data(self, force_refresh: bool = False) -> Dict:
        """
        Analyze GamePass data.
        
        Args:
            force_refresh: Force refresh data even if cache is fresh
            
        Returns:
            dict: Dictionary with analysis results
        """
        # Get data
        data = self.get_gamepass_data(force_refresh)
        
        # Безопасное получение данных с проверкой на None
        if data is None:
            data = {}
            
        ups_data = data.get('ups_data')
        if ups_data is None:
            ups_data = {}
            
        owner_data = data.get('owner_data', {})
        if owner_data is None:
            owner_data = {}
        
        # Sort tokens by UPS
        sorted_tokens = sorted(ups_data.items(), key=lambda x: x[1], reverse=True)
        
        # Get statistics
        total_tokens = 6969  # Total number of possible tokens
        active_tokens = len(ups_data)
        total_ups = sum(ups_data.values())
        avg_ups_per_active = total_ups / active_tokens if active_tokens else 0
        
        # Get wallet rankings (optional, based on owner data availability)
        wallet_rankings = self.get_wallet_rankings(ups_data, owner_data)
        
        # Безопасное получение last_update
        last_update = data.get('last_update')
        if last_update is None:
            last_update = time.time()
        
        return {
            'total_tokens': total_tokens,
            'active_tokens': active_tokens,
            'total_ups': total_ups,
            'avg_ups_per_active': avg_ups_per_active,
            'sorted_tokens': sorted_tokens,
            'wallet_rankings': wallet_rankings,
            'last_update': last_update,
            'has_owner_data': bool(owner_data),  # Flag to indicate if we have owner data
            'owner_data': owner_data  # Добавляем owner_data в возвращаемый словарь
        }
        
    def display_gamepass_analytics(self):
        """Display GamePass analytics in Streamlit"""
        st.header("GamePass Analytics")
        
        try:
            # Set up auto refresh every minute - message only
            current_time = time.time()
            
            # Initialize the session state if it doesn't exist
            if 'last_gamepass_refresh_time' not in st.session_state:
                st.session_state['last_gamepass_refresh_time'] = 0
                
            # Calculate time since last refresh
            time_since_refresh = current_time - st.session_state['last_gamepass_refresh_time']
            next_refresh = max(0, 60 - time_since_refresh)
            
            # Show refresh status
            st.write(f"Data auto-refreshes every minute (next refresh in {int(next_refresh)} seconds)")
            
            # Manual refresh button
            force_refresh = st.button("Refresh Now")
            if force_refresh:
                st.session_state['last_gamepass_refresh_time'] = 0  # Force refresh by resetting timer
            
            # Get and analyze data
            analysis = self.analyze_gamepass_data(force_refresh)
            
            # Display general statistics
            st.subheader("General Statistics")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Active Tokens (UPS > 0)", f"{analysis['active_tokens']} / {analysis['total_tokens']}")
            with col2:
                st.metric("Total UPS Generation", f"{self.format_token(analysis['total_ups'])}/sec")
            with col3:
                st.metric("Avg. UPS per Active Token", f"{self.format_token(analysis['avg_ups_per_active'])}/sec")
            
            # Add explanation of UPS
            st.info("UPS (Underlying Protocol Share) represents the token generation rate from the protocol.")
            
            # Display global wallet rankings if we have owner data
            has_owner_data = analysis.get('has_owner_data', False)
            
            # Always display the section but show a message if no data
            st.subheader("Global Wallet Rankings (Top 20)")
            if has_owner_data and analysis['wallet_rankings']['sorted_wallets']:
                wallet_data = []
                for rank, (wallet, total_wallet_ups) in enumerate(analysis['wallet_rankings']['sorted_wallets'][:20], 1):
                    token_count = len(analysis['wallet_rankings']['wallet_tokens'][wallet])
                    wallet_data.append({
                        "Rank": rank,
                        "Wallet": wallet,
                        "Total UPS": self.format_token(total_wallet_ups) + "/sec",
                        "Token Count": token_count
                    })
                
                if wallet_data:
                    wallet_df = pd.DataFrame(wallet_data)
                    st.dataframe(wallet_df, use_container_width=True, hide_index=True)
            else:
                st.warning("Ownership data is not available - wallet rankings cannot be shown")
            
            # Display global token rankings (always available)
            st.subheader("Global Token Rankings (Top 20)")
            
            token_data = []
            for rank, (token_id, ups) in enumerate(analysis['sorted_tokens'][:20], 1):
                owner = "Unknown"
                if has_owner_data:
                    owner = analysis['owner_data'].get(token_id, "Unknown")
                
                token_data.append({
                    "Rank": rank,
                    "Token ID": token_id,
                    "UPS": self.format_token(ups) + "/sec",
                    "Owner": owner if has_owner_data else "N/A"
                })
            
            if token_data:
                token_df = pd.DataFrame(token_data)
                st.dataframe(token_df, use_container_width=True, hide_index=True)
            else:
                st.info("No active tokens found")
            
            # Show last update time
            if analysis['last_update']:
                last_update_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(analysis['last_update']))
                st.caption(f"Last updated: {last_update_time}")
                
        except Exception as e:
            logger.error(f"Error displaying GamePass analytics: {e}")
            st.error(f"Failed to display GamePass analytics: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            st.info("Please check logs for detailed error information.") 
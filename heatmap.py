import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
from decimal import Decimal
import streamlit as st
from typing import List, Dict, Optional
import plotly.express as px
from loguru import logger
import time
import os
import json
import pickle

class HeatmapAnalyzer:
    def __init__(self):
        self.contract_address = "0x5487cb78417aa5923b80cdcf046a6554ca395874"
        self.api_key = "AVBDTC7X9DGP6IQK5RD8I6IK2666X1SPWF"
        self.base_url = "https://api.berascan.com/api"
        self._cached_data = None
        self._last_update = None
        self.cache_file = "heatmap_cache.pkl"
        logger.info(f"HeatmapAnalyzer initialized for contract {self.contract_address}")
        
        # Load cache if exists
        self._load_cache()
        
        # If cache not loaded, initialize data
        if self._cached_data is None:
            # Test API connection
            self._test_connection()
            
            # Initialize data loading
            logger.info("Starting initial data loading")
            self._init_data()
        else:
            # Update only the last hour of data
            self._update_latest_data()
    
    def _load_cache(self):
        """Load data from cache"""
        try:
            if os.path.exists(self.cache_file):
                logger.info(f"Loading data from cache: {self.cache_file}")
                with open(self.cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    self._cached_data = cache_data.get('data')
                    self._last_update = cache_data.get('last_update')
                    
                    if self._cached_data is not None and self._last_update is not None:
                        logger.info(f"Cache loaded successfully: {len(self._cached_data)} records, last update: {self._last_update}")
                        
                        # Check data freshness
                        if (datetime.now() - self._last_update).total_seconds() > 3600:
                            logger.info("Cache data is outdated, update required")
                            self._update_latest_data()
                    else:
                        logger.warning("Cache is corrupted or does not contain required data")
                        self._cached_data = None
                        self._last_update = None
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self._cached_data = None
            self._last_update = None
    
    def _save_cache(self):
        """Save data to cache"""
        try:
            if self._cached_data is not None and len(self._cached_data) > 0:
                logger.info(f"Saving data to cache: {self.cache_file}")
                cache_data = {
                    'data': self._cached_data,
                    'last_update': self._last_update
                }
                with open(self.cache_file, 'wb') as f:
                    pickle.dump(cache_data, f)
                logger.info(f"Cache saved successfully: {len(self._cached_data)} records")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _test_connection(self):
        """Test API connection"""
        try:
            logger.info("Testing Berascan API connection...")
            url = self.base_url
            params = {
                'module': 'proxy',
                'action': 'eth_blockNumber',
                'apikey': self.api_key
            }
            
            logger.info(f"Request: {url} with parameters {params}")
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Connection successful. Response: {data}")
                
                if data.get('status') == '1':
                    logger.info("API working correctly")
                else:
                    logger.warning(f"API returned error: {data.get('message', 'Unknown error')}")
            else:
                logger.error(f"API connection error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error testing connection: {e}")
        
    def _init_data(self):
        """Initial loading of data for heatmap"""
        try:
            current_time = datetime.now()
            current_day_of_week = current_time.weekday()
            
            # Load data for 7 days
            week_ago = current_time - timedelta(days=7)
            logger.info(f"Loading data from {week_ago.strftime('%Y-%m-%d %H:%M:%S')} to {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            transactions = self._get_transactions(week_ago, current_time)
            if transactions:
                self._cached_data = pd.DataFrame(transactions)
                self._last_update = current_time
                logger.info(f"Data loaded successfully, received {len(transactions)} transactions")
                
                # Clean old data considering current day of week
                self._clean_old_data(current_time)
                
                # Save to cache
                self._save_cache()
            else:
                logger.warning("Failed to get data for initialization")
        except Exception as e:
            logger.error(f"Error initializing data: {e}")
    
    def _update_latest_data(self):
        """Update data for the last hour"""
        try:
            current_time = datetime.now()
            
            if self._last_update is None:
                logger.warning("No information about last update, reinitializing data")
                self._init_data()
                return
                
            # If less than an hour passed, don't update
            if (current_time - self._last_update).total_seconds() < 3600:
                logger.info(f"Less than an hour since last update ({(current_time - self._last_update).total_seconds()/60:.1f} minutes), skipping update")
                return
                
            logger.info(f"Updating data for the last hour from {self._last_update.strftime('%Y-%m-%d %H:%M:%S')} to {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            transactions = self._get_transactions(self._last_update, current_time)
            if transactions:
                new_df = pd.DataFrame(transactions)
                self._cached_data = pd.concat([self._cached_data, new_df])
                logger.info(f"Added {len(transactions)} new transactions")
                
                # Clean old data
                self._clean_old_data(current_time)
                
                self._last_update = current_time
                
                # Save to cache
                self._save_cache()
            else:
                logger.info("No new transactions to add")
                self._last_update = current_time
        except Exception as e:
            logger.error(f"Error updating last hour data: {e}")
    
    def _clean_old_data(self, current_time):
        """Clean old data, considering current day of week"""
        try:
            if self._cached_data is None or len(self._cached_data) == 0:
                return
            
            current_day_of_week = current_time.weekday()
            
            # Remove data older than a week
            week_ago = current_time - timedelta(days=7)
            old_count = len(self._cached_data)
            
            # Filter data older than a week
            self._cached_data = self._cached_data[self._cached_data['timestamp'] >= week_ago]
            
            # Calculate day of week for each record
            self._cached_data['day_of_week'] = self._cached_data['timestamp'].dt.dayofweek
            
            # Get current date without time for comparison
            today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Remove data for the same day of week from previous week
            # Create mask for current week records
            days_to_prev_monday = current_day_of_week  # Days from current day to Monday
            current_week_start = today_date - timedelta(days=days_to_prev_monday)  # Monday of current week
            
            # Create mask: records with same day of week that are older than start of current week
            prev_week_mask = (
                (self._cached_data['day_of_week'] == current_day_of_week) & 
                (self._cached_data['timestamp'] < current_week_start)
            )
            
            # Apply filter
            self._cached_data = self._cached_data[~prev_week_mask]
            
            # For debugging: output data count by day of week
            day_counts = self._cached_data.groupby('day_of_week').size()
            logger.info(f"Record count by day of week after filtering: {day_counts.to_dict()}")
            
            # Clean temporary column
            if 'day_of_week' in self._cached_data.columns:
                self._cached_data = self._cached_data.drop(columns=['day_of_week'])
                
            new_count = len(self._cached_data)
            
            logger.info(f"Cleaned {old_count - new_count} outdated records, {new_count} remaining")
        except Exception as e:
            logger.error(f"Error cleaning old data: {e}")
        
    def _get_transactions(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get transactions for a time period"""
        logger.info(f"Requesting transactions from {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        transactions = []
        page = 1
        total_requests = 0
        
        while True:
            try:
                # Add delay between requests
                if total_requests > 0:
                    time.sleep(1)
                
                # Proper URL and parameter formatting
                url = self.base_url
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': self.contract_address,
                    'startblock': 0,
                    'endblock': 99999999,
                    'page': page,
                    'offset': 1000,
                    'sort': 'desc',
                    'apikey': self.api_key
                }
                
                logger.info(f"Sending request {total_requests+1} to API (page {page})")
                logger.info(f"URL: {url}")
                logger.info(f"Parameters: {params}")
                
                response = requests.get(url, params=params)
                total_requests += 1
                
                logger.info(f"Response status: {response.status_code}")
                
                if response.status_code == 429:
                    logger.warning("Rate limit exceeded, waiting 5 seconds...")
                    time.sleep(5)
                    continue
                    
                if response.status_code != 200:
                    logger.error(f"API error: {response.status_code} - {response.text}")
                    break
                    
                data = response.json()
                logger.info(f"Response received: status={data.get('status')}, message={data.get('message', 'No message')}")
                
                if data.get('status') != '1' or not data.get('result'):
                    if data.get('message') == 'No transactions found':
                        logger.info("No transactions found")
                    else:
                        logger.warning(f"API error: {data.get('message', 'Unknown error')}")
                    break
                
                logger.info(f"Received {len(data['result'])} transactions on page {page}")
                found_old_tx = False
                new_transactions = 0
                
                for tx in data['result']:
                    timestamp = datetime.fromtimestamp(int(tx['timeStamp']))
                    
                    if timestamp < start_time:
                        found_old_tx = True
                        continue
                        
                    if timestamp >= end_time:
                        continue
                        
                    value = Decimal(tx['value']) / Decimal(10**18)
                    transactions.append({
                        'transaction_id': tx['hash'],
                        'timestamp': timestamp,
                        'value': float(value),
                        'spanks': float(value) / 0.69
                    })
                    new_transactions += 1
                
                logger.info(f"Added {new_transactions} transactions for the specified period")
                
                if found_old_tx or len(data['result']) < params['offset']:
                    break
                    
                page += 1
                
            except Exception as e:
                logger.error(f"Error getting transactions: {str(e)}")
                break
                
        logger.info(f"Total received {len(transactions)} transactions in {total_requests} requests")
        return transactions

    def get_heatmap_data(self) -> pd.DataFrame:
        """Get and update heatmap data for spanks"""
        logger.info("Getting data for heatmap")
        
        # Update data for last hour if more than an hour passed
        current_time = datetime.now()
        if self._last_update is None or (current_time - self._last_update).total_seconds() > 3600:
            self._update_latest_data()
            
        # Process data for heatmap
        if self._cached_data is None or len(self._cached_data) == 0:
            logger.warning("No data for heatmap creation")
            return pd.DataFrame()
            
        df = self._cached_data.copy()
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        
        # For current day, keep only past hours
        current_day = current_time.weekday()
        current_hour_num = current_time.hour
        df = df[~((df['day_of_week'] == current_day) & (df['hour'] > current_hour_num))]
        
        # Create pivot table for spanks data
        heatmap_data = pd.pivot_table(
            df,
            values='spanks',
            index='hour',
            columns='day_of_week',
            aggfunc='sum',
            fill_value=0
        )
        
        logger.info(f"Heatmap data prepared, size: {heatmap_data.shape}")
        return heatmap_data

    def plot_heatmap(self):
        """Create heatmap using plotly express"""
        logger.info("Starting to plot heatmap")
        try:
            data = self.get_heatmap_data()
            
            if data.empty:
                logger.warning("No data to plot")
                st.warning("No data available for heatmap")
                return
                
            # Prepare data for plotting
            days_full = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            # Get current day of week
            current_time = datetime.now()
            current_day_of_week = current_time.weekday()
            
            # Define current week
            today_date = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            days_to_prev_monday = current_day_of_week
            current_week_start = today_date - timedelta(days=days_to_prev_monday)  # Monday of current week
            
            # For debugging: print available columns and their data
            logger.info(f"Available columns in data: {data.columns.tolist()}")
            logger.info(f"Current day of week: {current_day_of_week} ({days_full[current_day_of_week]})")
            
            # Create list of days to display with correct display of current day
            display_days = []
            day_indices = []
            
            for i in range(7):
                # Add this day if:
                # 1. It's not current day of week OR
                # 2. Data has column for current day (this is data for current week)
                if i in data.columns:
                    day_indices.append(i)
                    display_days.append(days_full[i])
            
            # Mapping original indices to new ones for display
            column_mapping = {old: idx for idx, old in enumerate(day_indices)}
            
            # Change column order for correct display
            if not data.empty:
                data = data[day_indices]
                # Rename columns to match days of week
                data.columns = range(len(data.columns))
            
            hours = [f"{h:02d}:00" for h in range(24)]
            
            # Check if data is empty after filtering
            if data.empty:
                logger.warning("No values to display after filtering")
                st.warning("No data available for heatmap display")
                return
                
            fig = px.imshow(
                data.values,
                labels=dict(x="Day of Week", y="Hour", color="Spanks Count"),
                x=display_days,
                y=hours,
                color_continuous_scale="YlOrRd",
                aspect="auto"
            )
            
            # Update layout
            fig.update_layout(
                title=f"Spanks Count Heatmap (excluding data from previous {days_full[current_day_of_week]})",
                xaxis_title="Day of Week",
                yaxis_title="Hour",
                height=600,
                yaxis=dict(autorange="reversed")
            )
            
            # Add hover template
            fig.update_traces(
                hovertemplate="Day: %{x}<br>Hour: %{y}<br>Spanks: %{z:.2f}<extra></extra>"
            )
            
            logger.info("Heatmap created successfully")
            st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            logger.error(f"Error in plot_heatmap: {str(e)}")
            st.error(f"Failed to create heatmap: {str(e)}")
            
    def find_optimal_time(self) -> None:
        """Find and display optimal 4-hour time range for contract interaction"""
        try:
            data = self.get_heatmap_data()
            if data.empty:
                st.warning("No data available for optimal time analysis")
                return
            
            # Create list of all possible 4-hour ranges
            time_ranges = []
            for start_hour in range(24):
                end_hour = (start_hour + 3) % 24
                time_ranges.append((start_hour, end_hour))
            
            # Find range with minimum activity
            min_activity = float('inf')
            optimal_range = None
            
            # For each range, calculate activity sum
            for start_hour, end_hour in time_ranges:
                # If range crosses midnight
                if start_hour > end_hour:
                    hours_to_check = list(range(start_hour, 24)) + list(range(0, end_hour + 1))
                else:
                    hours_to_check = list(range(start_hour, end_hour + 1))
                
                # Calculate activity sum for all days in this range
                total_activity = 0
                for hour in hours_to_check:
                    if hour in data.index:
                        total_activity += data.loc[hour].sum()
                
                if total_activity < min_activity:
                    min_activity = total_activity
                    optimal_range = (start_hour, end_hour)
            
            # Format time for display
            if optimal_range:
                start_hour, end_hour = optimal_range
                start_time = f"{start_hour:02d}:00"
                end_time = f"{end_hour:02d}:59"
                
                # If range crosses midnight
                if start_hour > end_hour:
                    time_range = f"{start_time} - 23:59, 00:00 - {end_time}"
                else:
                    time_range = f"{start_time} - {end_time}"
                
                st.info(f"Optimal time for contract interaction: {time_range}")
            else:
                st.warning("Could not determine optimal time")
                
        except Exception as e:
            logger.error(f"Error in find_optimal_time: {str(e)}")
            st.error(f"Failed to find optimal time: {str(e)}") 
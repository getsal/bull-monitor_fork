# Bullas Monitor

Monitoring and analytics of the GetQueue queue in the BeraChain network.

## Description

This project is a dashboard for monitoring and analysing the GetQueue queue in the BeraChain smart contract. The dashboard shows:

- General queue statistics
- Average queue strength
- Wallet statistics
- NFT statistics

## Setup

1. Clone the repository:
```bash
git clone https://github.com/your-username/bullas-monitor.git
cd bullas-monitor
```

2. Install dependencies:
````bash
pip install -r requirements.txt
```

## Usage

Start the dashboard:
````bash
streamlit run dashboard.py
```

## Configuration

The main configuration options are in the `dashboard.py` file:

- `CONTRACT_ADDRESS` - smart contract address
- `BERACHAIN_RPC` - BeraChain RPC endpoint
- `QUEUE_SIZE` - maximum queue size

## Licence

MIT

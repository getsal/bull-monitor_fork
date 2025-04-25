# Bullas Monitor

Мониторинг и аналитика очереди GetQueue в сети BeraChain.

## Описание

Этот проект представляет собой дашборд для мониторинга и анализа очереди GetQueue в смарт-контракте BeraChain. Дашборд показывает:

- Общую статистику очереди
- Среднюю силу очереди
- Статистику по кошелькам
- Статистику по NFT

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/bullas-monitor.git
cd bullas-monitor
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Использование

Запустите дашборд:
```bash
streamlit run dashboard.py
```

## Конфигурация

Основные параметры конфигурации находятся в файле `dashboard.py`:

- `CONTRACT_ADDRESS` - адрес смарт-контракта
- `BERACHAIN_RPC` - RPC endpoint BeraChain
- `QUEUE_SIZE` - максимальный размер очереди

## Лицензия

MIT 
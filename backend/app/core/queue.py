import asyncio

# asyncio.Queue already satisfies the EventQueue protocol (async put/get). Kafka-compatible queue replaces it later.
InProcQueue = asyncio.Queue

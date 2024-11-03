import argparse
import requests
import json
import v20
import signal
import sys
import time

def initialize_ohlc(instrument):
    """Initialize the OHLC data structure for an instrument."""
    ohlc_data[instrument] = {
        'o': None,
        'h': float('-inf'),
        'l': float('inf'),
        'c': None,
        'volume': 0,
        'start_time': time.time()  # Track the start time of the window
    }
    tick_count[instrument] = 0  # Track number of ticks (volume)
    
def update_ohlc(instrument, price):
    """Update OHLC data for each price update."""
    if ohlc_data[instrument]['o'] is None:
        # Set the open price on the first tick
        ohlc_data[instrument]['o'] = price

    # Update high, low, close, and volume
    ohlc_data[instrument]['h'] = max(ohlc_data[instrument]['h'], price)
    ohlc_data[instrument]['l'] = min(ohlc_data[instrument]['l'], price)
    ohlc_data[instrument]['c'] = price
    ohlc_data[instrument]['volume'] += 1
    tick_count[instrument] += 1

def reset_ohlc(instrument):
    """Reset OHLC data after the end of the window (e.g., 1 minute)."""
    print(f"\nInstrument: {instrument} - OHLC Data (Time Window Ended):")
    print(f"Open: {ohlc_data[instrument]['o']}, High: {ohlc_data[instrument]['h']}, Low: {ohlc_data[instrument]['l']}, Close: {ohlc_data[instrument]['c']}, Volume: {ohlc_data[instrument]['volume']}")

    # Reset the OHLC for the next time window
    ohlc_data[instrument] = {
        'o': None,
        'h': float('-inf'),
        'l': float('inf'),
        'c': None,
        'volume': 0,
        'start_time': time.time()  # Reset start time
    }
    tick_count[instrument] = 0  # Reset tick count (volume)

def process_forex_data(data):
    """Handle and process the incoming stream data, updating OHLC."""
    try:
        if 'price' in data:
            instrument = data['price']['instrument']
            bid_price = float(data['price']['bids'][0]['price'])

            # Update OHLC data for the instrument
            update_ohlc(instrument, bid_price)

            # Check if the time window (e.g., 1 minute) has elapsed
            current_time = time.time()
            if current_time - ohlc_data[instrument]['start_time'] >= 60:  # 60 seconds = 1 minute
                reset_ohlc(instrument)

    except KeyError:
        print("Error: Missing expected fields in data")
    except Exception as e:
        print(f"Unexpected error while processing data: {e}")

def stream_forex_data(account_id, api_key, stream_url):
    """Connect to OANDA API and stream live data, delegating OHLC processing to process_forex_data."""
    try:
        # Headers for authentication
        headers = {'Authorization': f'Bearer {api_key}',}

        # Parameters for the streaming request (select instruments to receive data for)
        params = {'instruments': "EUR_USD",}

        # Open a connection to the streaming API
        response = requests.get(stream_url, headers=headers, params=params, stream=True)

        # Check if connection is established
        if response.status_code != 200:
            print(f"Error connecting to streaming API: {response.status_code}")
            print(response.text)
            return

        # Initialize OHLC data for each instrument
        for instrument in params['instruments'].split(","):
            initialize_ohlc(instrument)

        # Stream the data line-by-line
        for line in response.iter_lines():
            print(f"Data received: {line}")
            if line:
                decoded_line = line.decode('utf-8')
                try:
                    # Parse the JSON data
                    data = json.loads(decoded_line)
                    
                    # Delegate the data processing to process_forex_data
                    process_forex_data(data)

                except json.JSONDecodeError:
                    print("Error decoding stream data")

    except requests.RequestException as e:
        print(f"Streaming error: {e}")


def signal_handler(sig, frame):
    print("\nReceived CTRL C\nExiting...")
    sys.exit(0)

# Register the signal handler for graceful exit on Ctrl + C
signal.signal(signal.SIGINT, signal_handler)

# OANDA API Streaming logic
def connect_to_oanda(account_id, access_token, instrument):
    try:
        """Connect to the OANDA API and stream live data."""
        api = v20.Context(
            'api-fxpractice.oanda.com',
            '443',
            token=access_token
        )

        response = api.pricing.stream(
            accountID=account_id,
            instruments=instrument
        )
        print("Done this succesfully")
        for msg_type, msg in response.parts():
            if msg_type == 'pricing.Price':
                print(f"Received OANDA data: {msg}")
    except Exception as e:
        print(e)

def stream_forex_data_mock():
    """Connect to the mock server and receive streaming OHLC data."""
    url = "http://localhost:5000/stream"
    response = requests.get(url, stream=True)
    
    # Check if connection is successful
    if response.status_code != 200:
        print(f"Error connecting to mock server: {response.status_code}")
        print(response.text)
        return

    # Initialize OHLC data for mock instruments (assuming the mock server sends these instruments)
    mock_instruments = ["EUR_USD", "USD_JPY"]
    for instrument in mock_instruments:
        initialize_ohlc(instrument)

    # Stream data line-by-line from the mock server
    for line in response.iter_lines():
        if line:
            print(f"Data received: {line}")
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith("data: "):
                json_data = decoded_line[6:]  # Strip 'data: ' prefix

                try:
                    # Parse the JSON data
                    data = json.loads(json_data)
                    
                    # Delegate the processing to process_forex_data
                    process_forex_data(data)

                except json.JSONDecodeError:
                    print("Error decoding mock data")


ohlc_data = {}
tick_count = {}
def main():

        
    # Argument parsing
    parser = argparse.ArgumentParser(description="Trading with OANDA")
    parser.add_argument('--mock', action='store_true', help="Connect to the mock server instead of OANDA API")
    args = parser.parse_args()

    with open('pyalgo.cfg', 'r') as file:
        config_lines = file.readlines()
    
    account_id = None
    access_token = None
    for line in config_lines:
        if 'account_id' in line:
            account_id = line.split('=')[1].strip()
        elif 'access_token' in line:
            access_token = line.split('=')[1].strip()

    # Define the instrument to stream (e.g., EUR_USD)
    instrument = "EUR_USD"
    
    account_type = 'practice'
    if account_type == 'practice':
        stream_url = "https://stream-fxpractice.oanda.com/v3/accounts/{}/pricing/stream".format(account_id)
    else:
        stream_url = "https://stream-fxtrade.oanda.com/v3/accounts/{}/pricing/stream".format(account_id)

    if args.mock:
        print("Connecting to mock server...")
        stream_forex_data_mock()
    else:
        print("Connecting to OANDA API...")
        if account_id and access_token:
            stream_forex_data(account_id, access_token, stream_url)
        else:
            print("Missing account_id or access_token in configuration file")

if __name__ == "__main__":
    main()

import argparse
import requests
import json
import v20
import signal
import sys
import time
import pandas as pd

def initialize_ohlc(instrument):
    """Initialize the OHLC data structure for an instrument."""
    ohlc_data[instrument] = {
        'o': None,
        'h': float('-inf'),
        'l': float('inf'),
        'c': None,
        'volume': 0,
        'start_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
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
    #print("Data:")
    #print(ohlc_data)

def reset_ohlc(instrument):
    """Reset OHLC data"""
    # Reset the OHLC for the next time window
    ohlc_data[instrument] = {
        'o': None,
        'h': float('-inf'),
        'l': float('inf'),
        'c': None,
        'volume': 0,
        'start_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    }
    tick_count[instrument] = 0  # Reset tick count (volume)

def process_forex_data(data, timeframe=60):
    """Process the incoming stream data, updating OHLC"""
    global ohlc_df
    try:
        if data.get('type') == 'PRICE':
            instrument = data['instrument']
            # Extract the first bid price
            if 'bids' in data and len(data['bids']) > 0:
                bid_price = float(data['bids'][0]['price'])

                update_ohlc(instrument, bid_price)

                # Check if the time window has elapsed
                current_time = time.time()
                t_struct = time.strptime(ohlc_data[instrument]['start_time'], '%Y-%m-%d %H:%M:%S')
                if current_time - time.mktime(t_struct) >= timeframe:
                    start_time = ohlc_data[instrument]['start_time']

                    open_price = ohlc_data[instrument]['o']
                    high_price = ohlc_data[instrument]['h']
                    low_price = ohlc_data[instrument]['l']
                    close_price = ohlc_data[instrument]['c']

                    new_row = pd.DataFrame({
                        'start_time': [start_time],
                        'open': [open_price],
                        'high': [high_price],
                        'low': [low_price],
                        'close': [close_price],
                        'volume': [ohlc_data[instrument]['volume']]
                    })

                    # Ensure the new row doesn't contain empty or all-NA entries
                    if not new_row.isna().all(axis=1).any():
                        # Append the new row to the existing DataFrame
                        ohlc_df = pd.concat([ohlc_df if not ohlc_df.empty else None, new_row], ignore_index=True)

                    # Print the updated DataFrame
                    print(f"\nInstrument: {instrument} - OHLC Data (Time Window Ended):")
                    print(f"\nUpdated OHLC DataFrame:\n{ohlc_df}\n")

                    # Save the DataFrame to a CSV file
                    ohlc_df.to_csv('ohlc_data.csv', index=False)

                    # Reset the OHLC data for the next time window
                    reset_ohlc(instrument)
            else:
                print("No bid data available for price update.")

    except KeyError as e:
        print(f"Error: Missing expected field {e} in data")
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
ohlc_df = pd.DataFrame(columns=['start_time', 'open', 'high', 'low', 'close', 'volume'])

def main():
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

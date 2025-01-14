import argparse
import requests
import json
import v20
import signal
import sys
import time
import pandas as pd
from datetime import datetime, time as dt_time
import pandas_ta as ta
import traceback

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

def process_forex_data(api_key, account_id, data, timeframe=60):
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
                        'o': [open_price],
                        'h': [high_price],
                        'l': [low_price],
                        'c': [close_price],
                        'volume': [ohlc_data[instrument]['volume']]
                    })

                    # Ensure the new row doesn't contain empty or all-NA entries
                    if not new_row.isna().all(axis=1).any():
                        # Append the new row to the existing DataFrame
                        ohlc_df = pd.concat([ohlc_df if not ohlc_df.empty else None, new_row], ignore_index=True)

                    #print(f"\nUpdated OHLC DataFrame:\n{ohlc_df}\n")

                    # Save the DataFrame to a CSV file
                    ohlc_df.to_csv('ohlc_data.csv', index=False)
                    # Calculate indicators
                    calculate_indicators(ohlc_df)
                    trade_based_on_rsi(api_key, account_id, instrument, sl=25, tp=25)

                    # Reset the OHLC data for the next time window
                    reset_ohlc(instrument)
            else:
                print("No bid data available for price update.")

    except KeyError as e:
        print(f"Error: Missing expected field {e} in data")
        traceback.print_exc()
    except Exception as e:
        print(f"Unexpected error while processing data: {e}")
        traceback.print_exc()

def stream_forex_data(account_id, api_key, stream_url, server_name):
    """Connect to OANDA API and receive streaming OHLC data."""
    try:
        print(f"Connecting to {server_name} server")
        # Parameters for the streaming request (instruments to receive data for)
        params = {'instruments': "EUR_USD",}

        # Open a connection to the streaming API
        response = requests.get(stream_url, headers=oanda_headers(api_key), params=params, stream=True)

        # Check if connection is established
        if response.status_code != 200:
            print(f"Error connecting to server:{server_name}\nError: {response.status_code}")
            print(response.text)
            return

        initialize_ohlc("EUR_USD")

        # Stream the data line-by-line
        for line in response.iter_lines():
            if line:
                #print(f"Data received: {line}")
                decoded_line = line.decode('utf-8')
                try:
                    data = json.loads(decoded_line)
                    process_forex_data(api_key, account_id, data)
                except json.JSONDecodeError:
                    print("Error decoding stream data")
                    traceback.print_exc()

    except requests.RequestException as e:
        print(f"Streaming error: {e}")
        traceback.print_exc()

def signal_handler(sig, frame):
    print("\nReceived CTRL C\nExiting...")
    sys.exit(0)

def calculate_indicators(ohlc_df):
    calculate_ema(ohlc_df, 10)
    calculate_sma(ohlc_df, 10)
    calculate_rsi(ohlc_df)
    print(ohlc_df[['start_time', 'c', 'ema_10', 'sma_10', 'RSI']])

def calculate_ema(ohlc_df, length):
    ohlc_df[f'ema_{length}'] = ta.ema(ohlc_df['c'], length=length)


def calculate_sma(ohlc_df, length):
    ohlc_df[f'sma_{length}'] = ta.sma(ohlc_df['c'], length=length)


def calculate_rsi(ohlc_df):
    ohlc_df['RSI'] = ta.rsi(ohlc_df['c'], length=14)

def oanda_headers(api_key):
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

def get_current_price(api_key, account_id, instrument):
    """Fetch the current bid/ask prices for an instrument."""
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{account_id}/pricing"
    params = {"instruments": instrument}
    response = requests.get(url, headers=oanda_headers(api_key), params=params)

    if response.status_code == 200:
        prices = response.json().get('prices', [])
        if prices:
            return prices[0]  # Return the first price for the instrument
        else:
            print("Price data not found.")
            return None
    else:
        print(f"Failed to fetch price data: {response.status_code} - {response.text}")
        return None

def place_order(api_key, account_id, instrument="EUR_USD", units=100, sl=None, tp=None):

    price_data = get_current_price(api_key, account_id, instrument)
    if not price_data:
        print("Not placing an order, no price")
        return None

    # Extract the bid/ask prices
    ask_price = price_data['asks'][0]['price']
    bid_price = price_data['bids'][0]['price']
    current_price = float(ask_price if units > 0 else bid_price)

    # Determine pip value (standard or JPY-specific)
    pip_value = 0.0001 if "JPY" not in instrument else 0.01

    # Calculate stop loss and take profit prices if provided
    stop_loss_price = current_price - (sl * pip_value) if sl is not None else None
    take_profit_price = current_price + (tp * pip_value) if tp is not None else None

    # Create the order data
    order_data = {
        "order": {
            "units": str(units),  # The size of the trade (positive for buy, negative for sell)
            "instrument": instrument,
            "timeInForce": "FOK",  # Fill-or-Kill
            "type": "MARKET",  # Market order
            "positionFill": "DEFAULT"  # Default position filling behavior
        }
    }

    # Add stop loss and take profit parameters to the order if they are provided
    if stop_loss_price:
        order_data['order']['stopLossOnFill'] = {"price": f"{stop_loss_price:.5f}"}
    if take_profit_price:
        order_data['order']['takeProfitOnFill'] = {"price": f"{take_profit_price:.5f}"}

    # OANDA API endpoint for placing an order
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{account_id}/orders"

    # Make the API request to place the order
    response = requests.post(url, headers=oanda_headers(api_key), json=order_data)
    if response.status_code == 201:
        print(f"Order placed successfully for {instrument}.")
        return response.json()
    else:
        print(f"Failed to place order: {response.status_code} - {response.text}")
        return None

def buy_order(api_key, account_id, instrument, units, sl, tp):
    return place_order(api_key, account_id, instrument, units, sl, tp)

def sell_order(api_key, account_id, instrument, units, sl, tp):
    return place_order(api_key, account_id, instrument, units*-1, sl, tp)

def get_account_balance(api_key, account_id):
    """Fetch the current balance of the OANDA account."""
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{account_id}/summary"
    response = requests.get(url, headers=oanda_headers(api_key))

    if response.status_code == 200:
        account_info = response.json().get('account', {})
        return float(account_info.get('balance', 0))
    else:
        print(f"Error fetching account balance: {response.status_code} - {response.text}")
        return None

def calculate_pos(api_key, account_id, leverage=15):
    balance = get_account_balance(api_key, account_id)
    return int(balance*leverage)

def should_trade():
    """Check if current time is within the allowed trading window (6am to 3pm UK) and only on weekdays (Monday to Friday)."""
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()  # Day of the week (0 = Monday, 6 = Sunday)

    # Define UK trading window: 6am to 3pm
    start_time = dt_time(6, 0)
    end_time = dt_time(22, 0)

    # Only trade if it's Monday to Friday and within the allowed time window
    if 0 <= current_day <= 4:
        if start_time <= current_time <= end_time:
            return True
    return False

def get_open_positions(api_key, account_id, instrument):
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{account_id}/openPositions"
    try:
        response = requests.get(url, headers=oanda_headers(api_key))
        if not response.json()['positions']:
            return None
        # Check if there is an open position for the given instrument
        for pos in response.json()['positions']:
            if pos['instrument'] == instrument:
                # Return the position type (buy/sell) and any other relevant data
                if float(pos['long']['units']) > 0:
                    return {'type': 'buy', 'units': pos['long']['units']}
                elif float(pos['short']['units']) < 0:
                    return {'type': 'sell', 'units': pos['short']['units']}
                else:
                    return None
        # If no position is found, return None
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching positions: {e}")
        return None

def trade_based_on_rsi(api_key, account_id, instrument, sl, tp):
    if ohlc_df.empty:
        return

    # Get the latest RSI value
    latest_rsi = ohlc_df['RSI'].iloc[-1]
    if latest_rsi == None:
        print("No rsi data. Not getting into a trade yet")
        return
    position = calculate_pos(api_key, account_id)
    if get_open_positions(api_key, account_id, instrument):
        print(f"There is an open position, not opening another one")
        return
    # Only proceed if we're in the correct trading hours
    if should_trade():
        # Check for a buy signal: RSI < 30 and no position open
        if latest_rsi < 30:
            print(f"RSI is {latest_rsi}. Entering buy position.")
            buy_order(api_key, account_id, instrument, position, sl, tp)

        # Check for a sell signal: RSI > 70 and no position open
        elif latest_rsi > 70:
            print(f"RSI is {latest_rsi}. Entering sell position.")
            sell_order(api_key, account_id, instrument, position, sl, tp)
    else:
        print("Outside of trading hours, no trades executed.")

ohlc_data = {}
tick_count = {}
ohlc_df = pd.DataFrame(columns=['start_time', 'o', 'h', 'l', 'c', 'volume'])


# Register the signal handler for graceful exit on Ctrl + C
signal.signal(signal.SIGINT, signal_handler)

def get_stream_url(account_type, mock, account_id):
    if account_type == 'practice':
        stream_url = f"https://stream-fxpractice.oanda.com/v3/accounts/{account_id}/pricing/stream"
    elif account_type == 'real':
        stream_url = f"https://stream-fxtrade.oanda.com/v3/accounts/{account_id}/pricing/stream"
    if mock:
        stream_url = "http://localhost:5000/stream"
    return stream_url

def get_config(config_file):
    account_id = None
    access_token = None
    with open(config_file, 'r') as file:
        config_lines = file.readlines()
    for line in config_lines:
        if 'account_id' in line:
            account_id = line.split('=')[1].strip()
        elif 'access_token' in line:
            access_token = line.split('=')[1].strip()
        elif 'account_type' in line:
            account_type =  line.split('=')[1].strip()
    return account_id, access_token, account_type

def main():
    parser = argparse.ArgumentParser(description="Trading with OANDA")
    parser.add_argument('--mock', action='store_true', help="Connect to the mock server instead of OANDA API")
    args = parser.parse_args()

    config_file = 'pyalgo.cfg'
    account_id, access_token, account_type = get_config(config_file)
    stream_url = get_stream_url(account_type, args.mock, account_id)

    if args.mock:
        stream_forex_data(account_id, access_token, stream_url, "mock")
    else:
        stream_forex_data(account_id, access_token, stream_url, "OANDA")


if __name__ == "__main__":
    main()

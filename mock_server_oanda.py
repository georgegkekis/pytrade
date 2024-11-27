import csv
import json
import time
import random
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# Path to your new CSV file
CSV_FILE_PATH = 'oanda_data_200_days_to_Nov_24.csv'

# Simulated account details
account_info = {
    "account": {
        "id": "001-001-1234567-001",
        "alias": "PracticeAccount",
        "currency": "USD",
        "balance": 100000.00,
        "openTradeCount": 1,
        "pendingOrderCount": 0,
        "pl": 0.00,
        "marginAvailable": 95000.00,
        "marginCloseoutPercentage": 0.1
    }
}

# Generate mock price data from CSV
def generate_mock_price_data(row):
    """Generate a mock price update in the same format as OANDA's live API based on the CSV row."""
    timestamp = row['time']
    open_price = float(row['o'])
    high_price = float(row['h'])
    low_price = float(row['l'])
    close_price = float(row['c'])   
    volume = int(row['volume'])
    complete = row['complete']

    # Generate random bid/ask prices around the close price
    bid_price = close_price - random.uniform(0.0001, 0.0005)
    ask_price = close_price + random.uniform(0.0001, 0.0005)

    # Generate random liquidity values
    liquidity = [500000, 2500000, 2000000, 5000000, 10000000]

    # Construct mock data
    data = {
        "type": "PRICE",
        "time": timestamp,
        "bids": [{"price": f"{bid_price:.5f}", "liquidity": random.choice(liquidity)} for _ in range(6)],
        "asks": [{"price": f"{ask_price:.5f}", "liquidity": random.choice(liquidity)} for _ in range(6)],
        "closeoutBid": f"{bid_price - 0.0001:.5f}",
        "closeoutAsk": f"{ask_price + 0.0001:.5f}",
        "status": "tradeable",
        "tradeable": True,
        "instrument": "EUR_USD"
    }

    return data

# Stream mock price data from CSV
def stream_mock_data():
    """Stream mock price data from the CSV file."""
    with open(CSV_FILE_PATH, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            data = generate_mock_price_data(row)
            yield f"{json.dumps(data)}\n\n"
            time.sleep(1)  # Simulate real-time streaming by adding a delay

# Endpoints

@app.route('/stream')
def stream():
    """Stream mock price data."""
    return Response(stream_mock_data(), mimetype='text/event-stream')

@app.route('/v3/accounts/<account_id>', methods=['GET'])
def get_account_info(account_id):
    """Return mock account details."""
    if account_id == account_info['account']['id']:
        return jsonify(account_info)
    else:
        return jsonify({"error": "Account not found"}), 404

@app.route('/v3/accounts/<account_id>/pricing', methods=['GET'])
def get_current_price(account_id):
    """Return current price from CSV data for a specific instrument."""
    instrument = request.args.get('instruments')
    if instrument != "EUR_USD":
        return jsonify({"error": "Instrument not supported"}), 400

    with open(CSV_FILE_PATH, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            data = generate_mock_price_data(row)
            return jsonify({"prices": [data]})

    return jsonify({"error": "No data available"}), 404

@app.route('/v3/accounts/<account_id>/orders', methods=['POST'])
def place_order(account_id):
    """Simulate placing an order."""
    if account_id != account_info['account']['id']:
        return jsonify({"error": "Account not found"}), 404

    order_data = request.json.get("order")
    if not order_data:
        return jsonify({"error": "Invalid order data"}), 400

    # Extract order details
    instrument = order_data.get("instrument", "EUR_USD")
    units = int(order_data.get("units", 0))
    stop_loss = order_data.get("stopLossOnFill", {}).get("price")
    take_profit = order_data.get("takeProfitOnFill", {}).get("price")

    # Mock a successful order response
    order_response = {
        "orderCreateTransaction": {
            "type": "MARKET_ORDER",
            "instrument": instrument,
            "units": units,
            "timeInForce": order_data.get("timeInForce", "FOK"),
            "priceBound": None,
            "positionFill": order_data.get("positionFill", "DEFAULT"),
            "stopLossOnFill": stop_loss,
            "takeProfitOnFill": take_profit,
            "reason": "CLIENT_ORDER"
        },
        "orderFillTransaction": {
            "price": random.uniform(1.10, 1.20),
            "units": units,
            "instrument": instrument,
            "pl": random.uniform(-100, 100)
        }
    }

    # Simulate account balance update
    account_info['account']['balance'] += order_response["orderFillTransaction"]["pl"]

    return jsonify(order_response)

@app.route('/v3/accounts/<account_id>/trades', methods=['GET'])
def get_open_trades(account_id):
    """Simulate fetching open trades."""
    if account_id != account_info['account']['id']:
        return jsonify({"error": "Account not found"}), 404

    open_trades = [{
        "instrument": "EUR_USD",
        "units": 1000,
        "price": 1.17500,
        "unrealizedPL": 50.00,
        "state": "OPEN"
    }]

    return jsonify({"trades": open_trades})

if __name__ == "__main__":
    app.run(debug=True, port=5000)


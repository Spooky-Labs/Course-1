#!/usr/bin/env python3
import backtrader as bt
import backtrader.analyzers as btanalyzers # Import analyzers
import pandas as pd
import datetime  # For datetime objects
import sys
import os
import json  # Import the json library
import math # For checking NaN

from agent.agent import Agent

# Data directory within the container/workspace
# This data MUST be populated during the build process, not at runtime.
CACHE_DIR = "/data" # Use absolute path matching build step
# OUTPUT_FILE = "/workspace/output.json"  # Output file path
OUTPUT_FILE = "results.json" # Path *inside* the container
# CACHE_DIR = "data"
# OUTPUT_FILE = "./output.json"  # Output file path
STARTING_CASH = 10000.0

# os.makedirs(CACHE_DIR, exist_ok=True)


def run_backtest(symbols, start_date, end_date, risk_free_rate=0.0):
    """
    Runs the backtest and returns results as a dictionary.
    Expects data to be pre-cached in CACHE_DIR.
    """
    results_data = {
        "parameters": {
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
        },
        "results": {},
        "error": None,
    }

    try:
        cerebro = bt.Cerebro()
        cerebro.addstrategy(Agent)
        cerebro.broker.setcash(STARTING_CASH)

        # --- Add Analyzers ---
        cerebro.addanalyzer(btanalyzers.SharpeRatio, _name='sharpe', riskfreerate=risk_free_rate, timeframe=bt.TimeFrame.Days, compression=1) # Adjust timeframe/compression as needed
        cerebro.addanalyzer(btanalyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(btanalyzers.TradeAnalyzer, _name='trades')
        cerebro.addanalyzer(btanalyzers.Returns, _name='returns')
        cerebro.addanalyzer(btanalyzers.Calmar, _name='calmar') # Added Calmar
        cerebro.addanalyzer(btanalyzers.SQN, _name='sqn') # Added SQN
        cerebro.addanalyzer(btanalyzers.AnnualReturn, _name='annualreturn') # Added AnnualReturn

        for symbol in symbols:

            # Create a Data Feed
            data_feed = bt.feeds.GenericCSVData(
                dataname=f'data/{symbol}.csv', # Path to your CSV file

                # Define the column mapping - Backtrader needs to know which column is which
                # These column numbers assume the date is column 0 (the index saved by pandas)
                datetime=0,
                open=1,
                high=2,
                low=3,
                close=4,
                volume=6, # Note: Volume is column 6 if Adj Close is column 5
                openinterest=-1, # -1 indicates column is not present
                adjusted=5, # Specify the column number for adjusted close

                # Specify the date format if needed (pandas usually saves in a recognizable format)
                dtformat=('%Y-%m-%d %H:%M:%S%z'), # Example: 2023-10-27

                fromdate=datetime.datetime.strptime(start_date, '%Y-%m-%d'), # Optional: Start date
                todate=datetime.datetime.strptime(end_date, '%Y-%m-%d')  # Optional: End date
            )
            cerebro.adddata(data_feed, name=f'{symbol}') # Giving it a name is good practice
            
        # Run backtest
        # print("Running backtest...")
        initial_value = cerebro.broker.getvalue()
        results = cerebro.run()
        final_value = cerebro.broker.getvalue()
        portfolio_return_pct = ((final_value - initial_value) / initial_value) * 100 if initial_value != 0 else 0
        # Calculate overall portfolio return %
        portfolio_pnl = final_value - initial_value
        # print("Backtest finished.")
        
        # --- Retrieve and format analysis results ---
        strategyResult = results[0] # Get the first strategy instance
        sharpe_analysis = strategyResult.analyzers.sharpe.get_analysis()
        drawdown_analysis = strategyResult.analyzers.drawdown.get_analysis()
        trade_analysis = strategyResult.analyzers.trades.get_analysis()
        returns_analysis = strategyResult.analyzers.returns.get_analysis()
        calmar_analysis = strategyResult.analyzers.calmar.get_analysis() # Get Calmar
        sqn_analysis = strategyResult.analyzers.sqn.get_analysis() # Get SQN
        annual_return_analysis = strategyResult.analyzers.annualreturn.get_analysis() # Get AnnualReturn

        # Helper function to safely get metric, handling None analysis objects
        def safe_get(analysis, keys, default=None):
            if analysis is None: return default
            if not isinstance(keys, (list, tuple)): keys = [keys]
            val = analysis
            try:
                for k in keys:
                    if isinstance(val, dict): val = val.get(k)
                    else: val = getattr(val, k, None)
                    if val is None: return default
                # Check for NaN specifically if the result might be float
                if isinstance(val, float) and math.isnan(val): return default
                return val
            except (AttributeError, KeyError):
                return default

        # Consolidate results
        results_data["results"] = {
            "initial_value": initial_value,
            "final_value": final_value,
            "portfolio_return_pct": portfolio_return_pct, # Overall portfolio return
            "portfolio_net_pnl": portfolio_pnl,           # Overall portfolio PnL
            "annualized_return_pct": safe_get(returns_analysis, 'rannually'), # From Returns analyzer            "annualized_return_pct": safe_get(returns_analysis, 'rannually'),

            # Risk-Adjusted (often based on overall returns)
            "sharpe_ratio": safe_get(sharpe_analysis, 'sharperatio'),
            "calmar_ratio": safe_get(calmar_analysis, 'calmar'),      # Added
            "sqn": safe_get(sqn_analysis, 'sqn'),                    # Added

            # Trade Stats (Specific to Closed Trades from TradeAnalyzer)
            "max_drawdown_pct": safe_get(drawdown_analysis, ['max', 'drawdown']),
            "max_drawdown_money": safe_get(drawdown_analysis, ['max', 'moneydown']),
            "max_drawdown_duration_bars": safe_get(drawdown_analysis, ['max', 'len']), # Added duration

            # Trade Stats (Specific to Closed Trades from TradeAnalyzer)
            "total_trades": safe_get(trade_analysis, ['total', 'total'], 0),
            "trades_open": safe_get(trade_analysis, ['total', 'open'], 0),
            "trades_closed": safe_get(trade_analysis, ['total', 'closed'], 0),
            "win_trades": safe_get(trade_analysis, ['won', 'total'], 0),
            "loss_trades": safe_get(trade_analysis, ['lost', 'total'], 0),
            "win_rate_pct": (safe_get(trade_analysis, ['won', 'total'], 0) / safe_get(trade_analysis, ['total', 'closed'], 1) * 100) \
                            if safe_get(trade_analysis, ['total', 'closed']) > 0 else 0, # Avoid division by zero
            "total_net_pnl": safe_get(trade_analysis, ['pnl', 'net', 'total'], 0),
            "average_win_pnl": safe_get(trade_analysis, ['won', 'pnl', 'average'], 0),
            "average_loss_pnl": safe_get(trade_analysis, ['lost', 'pnl', 'average'], 0),
            "profit_factor": abs(safe_get(trade_analysis, ['won', 'pnl', 'total'], 0) / safe_get(trade_analysis, ['lost', 'pnl', 'total'], 1)) \
                             if safe_get(trade_analysis, ['lost', 'pnl5', 'total']) != 0 else None, # Avoid division by zero
            "max_consecutive_wins": safe_get(trade_analysis, ['streak', 'won', 'longest'], 0), # Added
            "max_consecutive_losses": safe_get(trade_analysis, ['streak', 'lost', 'longest'], 0), # Added
            "average_trade_duration_bars": safe_get(trade_analysis, ['len', 'average']), # Added duration

            # Annual Returns (dictionary)
            "annual_returns": annual_return_analysis, # Added
        }

        # --- Updated Printing ---
        # print("\n------ Backtest Summary ------")
        # print(f"Period: {start_date} to {end_date}")
        # print(f"Initial Portfolio Value: ${initial_value:.2f}")
        # print(f"Final Portfolio Value: ${final_value:.2f}")
        # print(f"Portfolio Net PnL: ${portfolio_pnl:.2f}")
        # print(f"Portfolio Return: {portfolio_return_pct:.2f}%")
        # print("-" * 24)
        # print("Performance Metrics:")
        # print(f"  Sharpe Ratio: {results_data['results'].get('sharpe_ratio', 'N/A')}")
        # print(f"  Calmar Ratio: {results_data['results'].get('calmar_ratio', 'N/A')}")
        # print(f"  Max Drawdown: {results_data['results'].get('max_drawdown_pct', 'N/A'):.2f}%")
        # print(f"  Max Drawdown Duration (bars): {results_data['results'].get('max_drawdown_duration_bars', 'N/A')}")
        # print("-" * 24)
        # print("Closed Trade Analysis:")
        # print(f"  SQN (System Quality Number): {results_data['results'].get('sqn', 'N/A')}")
        # print(f"  Total Trades Closed: {results_data['results'].get('trades_closed', 'N/A')}")
        # print(f"  Win Rate: {results_data['results'].get('win_rate_pct', 'N/A'):.2f}%")
        # print(f"  Profit Factor: {results_data['results'].get('profit_factor', 'N/A')}")
        # print("-" * 30)

    except Exception as e:
        print(f"ERROR during backtest: {e}", file=sys.stderr)
        results_data["error"] = str(e)
        # Re-raise the exception so the script exits with an error
        raise

    return results_data

def save_results_to_json(filepath, data):
    """Saves the results dictionary to a JSON file."""
    print(f"Attempting to save results to {filepath}...")
    try:
        # Ensure the directory exists (though /workspace should always exist in Cloud Build)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4) # Use indent for readability
        print(f"Successfully saved results to {filepath}")
    except Exception as e:
        print(f"ERROR saving results to {filepath}: {e}", file=sys.stderr)
        # Re-raise the exception to indicate failure
        raise


if __name__ == "__main__":
    with open("symbols.txt", "r") as file:
        lines = file.readlines()  # Read all lines into a list
        symbols = [line.replace("\n", "") for line in lines]

    # Use a 2-year window for faster backtesting (adjust as needed)
    # Longer periods = more accurate but slower (each bar runs ML inference)
    start_date = "2023-01-01"
    end_date = "2024-12-31"
    # Define risk-free rate for Sharpe Ratio (e.g., 0% or approximate T-bill rate)
    risk_free_rate = 0.01 # Example: 1% annual rate

    final_results = {}
    exit_code = 0

    try:
        # Run the backtest
        final_results = run_backtest(
            symbols, start_date, end_date,
            risk_free_rate=risk_free_rate
        )

        # Output results: File (Cloud Batch) or stdout (Cloud Build docker run)
        # Cloud Batch mounts GCS via gcsfuse - container writes locally, syncs to GCS
        output_dir = os.environ.get('OUTPUT_DIR')

        if output_dir:
            # Write to mounted GCS volume (Cloud Batch environment)
            # The volume is mounted via gcsfuse at VM level - container sees local filesystem
            output_path = os.path.join(output_dir, 'output.json')
            with open(output_path, 'w') as f:
                json.dump(final_results, f, indent=None, separators=(',', ':'), default=str)
            print(f"Results written to {output_path}")
        else:
            # Fallback: print to stdout (for local testing / Cloud Build docker run)
            print(json.dumps(final_results, indent=None, separators=(',', ':'), default=str))

    except Exception as json_e:
        # If any part fails, try to save an error state (optional)
        # if not final_results: # If run_backtest failed before returning
        #      final_results = { "parameters": { "symbols": symbols, "start_date": start_date, "end_date": end_date}, "error": f"Script failed early: {e}" }
        # elif not final_results.get("error"): # If run_backtest succeeded but saving failed
        #      final_results["error"] = f"Failed to save results: {e}"
        # # Try saving error state (best effort)
        # try:
        #     save_results_to_json(OUTPUT_FILE, final_results)
        # except:
        #      print("Failed even to save error state to JSON.", file=sys.stderr)
        # If JSON serialization fails, print an error message to stderr
        print(f"FATAL: Failed to serialize results to JSON: {json_e}", file=sys.stderr)
        # Print a basic error JSON to stdout as a fallback
        print(json.dumps({"error": f"JSON serialization failed: {json_e}", "partial_results": str(final_results)}))
        exit_code = 1 # Signal failure to Cloud Build

    # print(f"Exiting with code {exit_code}")
    sys.exit(exit_code) # Ensure Cloud Build knows if the step succeeded or failed
import pandas as pd
import os
import numpy as np
from flask import Flask, jsonify, abort, render_template, request

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'dataset')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output') 

plays_with_predictions_df = None
try:
    print("Carregando banco de dados de jogadas com previsões...")
    
    predictions_filepath = os.path.join(OUTPUT_DIR, 'plays_with_predictions.parquet')
    plays_with_predictions_df = pd.read_parquet(predictions_filepath)
    
    players_df = pd.read_parquet(os.path.join(DATA_PATH, "players.parquet"))
    games_df = pd.read_parquet(os.path.join(DATA_PATH, "games.parquet"))
    
    plays_with_predictions_df = plays_with_predictions_df.merge(
        players_df[['nflId', 'displayName']], 
        left_on='ballCarrierId', 
        right_on='nflId', 
        how='left'
    )
    print(f"Dados carregados com sucesso de '{predictions_filepath}'. A API está pronta.")
except FileNotFoundError:
    print(f"\nERRO FATAL: Arquivo 'plays_with_predictions.parquet' não encontrado em '{OUTPUT_DIR}'.")
    print("Execute 'python batch_predict.py' primeiro para gerar este arquivo.\n")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/search_filters')
def get_search_filters():
    if plays_with_predictions_df is None: return jsonify({"error": "Dados de busca não disponíveis."}), 503
    filters = {'players': sorted(plays_with_predictions_df.dropna(subset=['displayName'])['displayName'].unique().tolist()), 'teams': sorted(plays_with_predictions_df['possessionTeam'].unique().tolist())}
    return jsonify(filters)

@app.route('/api/search')
def search_plays():
    if plays_with_predictions_df is None: return jsonify({"error": "Dados de busca não disponíveis."}), 503
    results = plays_with_predictions_df.copy()
    team = request.args.get('team')
    player_name = request.args.get('player_name')
    down = request.args.get('down', type=int)
    if team: results = results[results['possessionTeam'] == team]
    if player_name: results = results[results['displayName'] == player_name]
    if down: results = results[results['down'] == down]
    results = results.sort_values(by='predictedYardsGained', ascending=False).head(50)
    cols_to_return = ['gameId', 'playId', 'playDescription', 'displayName', 'prePenaltyYardsGained', 'predictedYardsGained']
    results = results[[col for col in cols_to_return if col in results.columns]]
    results['predictedYardsGained'] = results['predictedYardsGained'].round(2)
    results['prePenaltyYardsGained'] = results['prePenaltyYardsGained'].round(2)
    return jsonify(results.to_dict(orient='records'))

@app.route('/api/play_data/game/<int:game_id>/play/<int:play_id>')
def get_play_data(game_id, play_id):
    if plays_with_predictions_df is None: return jsonify({"error": "Dados não disponíveis."}), 503
    play_info_row = plays_with_predictions_df[(plays_with_predictions_df['gameId'] == game_id) & (plays_with_predictions_df['playId'] == play_id)]
    if play_info_row.empty: abort(404, "Jogada não encontrada.")
    play_info_series = play_info_row.iloc[0]
    safe_play_info = play_info_series.replace({np.nan: None})
    play_info = safe_play_info.to_dict()
    week = games_df[games_df['gameId'] == game_id].iloc[0]['week']
    tracking_file = os.path.join(DATA_PATH, f'tracking_week_{week}.parquet')
    if not os.path.exists(tracking_file): abort(404, f"Arquivo de rastreamento para a semana {week} não encontrado.")
    tracking_week_df = pd.read_parquet(tracking_file)
    play_tracking_data = tracking_week_df[(tracking_week_df['gameId'] == game_id) & (tracking_week_df['playId'] == play_id)]
    safe_tracking_data = play_tracking_data.replace({np.nan: None})
    return jsonify({'playInfo': play_info, 'trackingData': safe_tracking_data.to_dict(orient='records')})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
import pandas as pd
import numpy as np
import joblib
from tqdm import tqdm
from scipy.spatial import ConvexHull
import warnings
import os 

warnings.filterwarnings('ignore', category=FutureWarning)

print("Iniciando processo de PREVISÃO EM LOTE...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'dataset')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output') 

print("Carregando modelo, colunas e dados base...")
try:
    model = joblib.load(os.path.join(OUTPUT_DIR, 'play_yardage_predictor_advanced.joblib'))
    model_columns = joblib.load(os.path.join(OUTPUT_DIR, 'model_columns_advanced.joblib'))
    
    plays_df = pd.read_parquet(os.path.join(DATA_PATH, "plays.parquet"))
    games_df = pd.read_parquet(os.path.join(DATA_PATH, "games.parquet"))
    player_play_df = pd.read_parquet(os.path.join(DATA_PATH, "player_play.parquet"))
except FileNotFoundError as e:
    print(f"Erro: Arquivo necessário não encontrado: {e}. Abortando.")
    print("Certifique-se de executar 'train_model_advanced.py' primeiro.")
    exit()

print("Recriando features para todo o dataset...")

ball_carriers = player_play_df[(player_play_df['hadRushAttempt'] == 1) | (player_play_df['hadPassReception'] == 1)]
ball_carriers = ball_carriers[['gameId', 'playId', 'nflId']].rename(columns={'nflId': 'ballCarrierId'})
plays_df = plays_df.merge(ball_carriers, on=['gameId', 'playId'], how='left')
plays_df.dropna(subset=['ballCarrierId'], inplace=True)
plays_df['ballCarrierId'] = plays_df['ballCarrierId'].astype(int)
player_performance = plays_df.groupby('ballCarrierId')['prePenaltyYardsGained'].agg(['mean', 'count']).reset_index()
player_performance.rename(columns={'mean': 'carrier_avg_yards', 'count': 'carrier_play_count'}, inplace=True)
player_performance = player_performance[player_performance['carrier_play_count'] > 20]
plays_df = plays_df.merge(player_performance[['ballCarrierId', 'carrier_avg_yards']], on='ballCarrierId', how='left')
plays_df['carrier_avg_yards'].fillna(plays_df['prePenaltyYardsGained'].mean(), inplace=True)
plays_df = plays_df.merge(games_df[['gameId', 'week']], on='gameId', how='left')
tracking_cache = {}
def get_tracking_data_for_play(game_id, play_id, week):
    if week not in tracking_cache:
        try: tracking_cache[week] = pd.read_parquet(f"{DATA_PATH}tracking_week_{week}.parquet")
        except FileNotFoundError: return None
    return tracking_cache[week][(tracking_cache[week]['gameId'] == game_id) & (tracking_cache[week]['playId'] == play_id)]
def calculate_tracking_features(play_tracking_data, play_info):
    snap_frame_row = play_tracking_data[play_tracking_data['event'] == 'ball_snap']
    if snap_frame_row.empty: return {}
    snap_frame_id = snap_frame_row.iloc[0]['frameId']
    line_of_scrimmage = snap_frame_row.iloc[0]['x']
    players_at_snap = play_tracking_data[play_tracking_data['frameId'] == snap_frame_id]
    offense_team = players_at_snap[players_at_snap['club'] == play_info['possessionTeam']]
    defense_team = players_at_snap[players_at_snap['club'] == play_info['defensiveTeam']]
    features = {}
    if len(offense_team) > 2:
        try: features['offense_area'] = ConvexHull(offense_team[['x', 'y']]).volume
        except Exception: features['offense_area'] = np.nan
    box_min_x, box_max_x = line_of_scrimmage - 1, line_of_scrimmage + 7
    box_min_y, box_max_y = 15, 53.3 - 15
    defenders_in_box = defense_team[(defense_team['x'].between(box_min_x, box_max_x)) & (defense_team['y'].between(box_min_y, box_max_y))]
    features['defenders_in_box'] = len(defenders_in_box)
    return features
all_play_features = []
for _, play in tqdm(plays_df.iterrows(), total=len(plays_df)):
    tracking_data = get_tracking_data_for_play(play['gameId'], play['playId'], play['week'])
    tracking_features = {}
    if tracking_data is not None and not tracking_data.empty:
        tracking_features = calculate_tracking_features(tracking_data, play)
    base_features = {'gameId': play['gameId'], 'playId': play['playId'], 'down': play['down'], 'yardsToGo': play['yardsToGo'], 'quarter': play['quarter'], 'playAction': play['playAction'], 'possessionTeam': play['possessionTeam'], 'defensiveTeam': play['defensiveTeam'], 'offenseFormation': play['offenseFormation'], 'receiverAlignment': play['receiverAlignment'], 'carrier_avg_yards': play['carrier_avg_yards']}
    base_features.update(tracking_features)
    all_play_features.append(base_features)
features_df = pd.DataFrame(all_play_features).dropna()

print("Preparando dados para previsão...")
ids_df = features_df[['gameId', 'playId']]
features_for_model = features_df.drop(columns=['gameId', 'playId'])
X_encoded = pd.get_dummies(features_for_model, columns=['possessionTeam', 'defensiveTeam', 'offenseFormation', 'receiverAlignment'], dummy_na=True)
X_aligned = X_encoded.reindex(columns=model_columns, fill_value=0)

print("Fazendo previsões em todo o dataset...")
predictions = model.predict(X_aligned)

results_df = ids_df.copy()
results_df['predictedYardsGained'] = predictions
final_plays_df = plays_df.merge(results_df, on=['gameId', 'playId'], how='inner')

output_filename = os.path.join(OUTPUT_DIR, 'plays_with_predictions.parquet')
final_plays_df.to_parquet(output_filename, index=False)

print(f"\nProcesso concluído! As jogadas com as previsões foram salvas em '{output_filename}'.")
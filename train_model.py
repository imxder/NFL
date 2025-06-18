import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib
from tqdm import tqdm
from scipy.spatial import ConvexHull
import warnings
import os 

warnings.filterwarnings('ignore', category=FutureWarning)

print("Iniciando o processo de treinamento do MODELO AVANÇADO (v3)...")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'dataset')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True) 

try:
    plays_df = pd.read_parquet(os.path.join(DATA_PATH, "plays.parquet"))
    games_df = pd.read_parquet(os.path.join(DATA_PATH, "games.parquet"))
    player_play_df = pd.read_parquet(os.path.join(DATA_PATH, "player_play.parquet"))
    print("Arquivos base carregados.")
except FileNotFoundError as e:
    print(f"Erro: Arquivo base não encontrado: {e}. Abortando.")
    exit()

print("Identificando o portador da bola...")
ball_carriers = player_play_df[(player_play_df['hadRushAttempt'] == 1) | (player_play_df['hadPassReception'] == 1)]
ball_carriers = ball_carriers[['gameId', 'playId', 'nflId']].rename(columns={'nflId': 'ballCarrierId'})
plays_df = plays_df.merge(ball_carriers, on=['gameId', 'playId'], how='left')
plays_df.dropna(subset=['ballCarrierId'], inplace=True)
plays_df['ballCarrierId'] = plays_df['ballCarrierId'].astype(int)

print("Calculando proxy de habilidade do jogador...")
player_performance = plays_df.groupby('ballCarrierId')['prePenaltyYardsGained'].agg(['mean', 'count']).reset_index()
player_performance.rename(columns={'mean': 'carrier_avg_yards', 'count': 'carrier_play_count'}, inplace=True)
player_performance = player_performance[player_performance['carrier_play_count'] > 20]
plays_df = plays_df.merge(player_performance[['ballCarrierId', 'carrier_avg_yards']], on='ballCarrierId', how='left')
plays_df['carrier_avg_yards'].fillna(plays_df['prePenaltyYardsGained'].mean(), inplace=True)

plays_df = plays_df.merge(games_df[['gameId', 'week']], on='gameId', how='left')
tracking_cache = {}

def get_tracking_data_for_play(game_id, play_id, week):
    if week not in tracking_cache:
        try:
            tracking_cache[week] = pd.read_parquet(f"{DATA_PATH}tracking_week_{week}.parquet")
        except FileNotFoundError: return None
    tracking_df = tracking_cache[week]
    return tracking_df[(tracking_df['gameId'] == game_id) & (tracking_df['playId'] == play_id)]

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

print("Iniciando engenharia de features...")
all_play_features = []
for _, play in tqdm(plays_df.iterrows(), total=len(plays_df)):
    tracking_data = get_tracking_data_for_play(play['gameId'], play['playId'], play['week'])
    if tracking_data is None or tracking_data.empty: continue
    tracking_features = calculate_tracking_features(tracking_data, play)
    base_features = {'down': play['down'], 'yardsToGo': play['yardsToGo'], 'quarter': play['quarter'], 'playAction': play['playAction'], 'possessionTeam': play['possessionTeam'], 'defensiveTeam': play['defensiveTeam'], 'offenseFormation': play['offenseFormation'], 'receiverAlignment': play['receiverAlignment'], 'carrier_avg_yards': play['carrier_avg_yards'], 'prePenaltyYardsGained': play['prePenaltyYardsGained']}
    base_features.update(tracking_features)
    all_play_features.append(base_features)

print(f"\nEngenharia de features concluída. Total de jogadas processadas: {len(all_play_features)}")
final_df = pd.DataFrame(all_play_features).dropna()
target = 'prePenaltyYardsGained'
features = [col for col in final_df.columns if col != target]
categorical_features = ['possessionTeam', 'defensiveTeam', 'offenseFormation', 'receiverAlignment']
X = pd.get_dummies(final_df[features], columns=categorical_features, dummy_na=True)
y = final_df[target]
print("Iniciando o treinamento do modelo final...")
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = lgb.LGBMRegressor(objective='regression_l1', n_estimators=1000, learning_rate=0.05, num_leaves=31, random_state=42, n_jobs=-1)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], eval_metric='mae', callbacks=[lgb.early_stopping(100, verbose=True)])

predictions = model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)
print(f"\n--- Avaliação Final do Modelo Avançado (v3) ---")
print(f"Erro Médio Absoluto (MAE): {mae:.2f} jardas")

model_filename = os.path.join(OUTPUT_DIR, 'play_yardage_predictor_advanced.joblib')
columns_filename = os.path.join(OUTPUT_DIR, 'model_columns_advanced.joblib')

joblib.dump(model, model_filename)
joblib.dump(X.columns.tolist(), columns_filename)

print(f"\nModelo AVANÇADO salvo em '{model_filename}'")
print(f"Colunas do modelo AVANÇADO salvas em '{columns_filename}'")
print("Processo concluído com sucesso!")
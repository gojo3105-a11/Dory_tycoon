using System;
using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// Generic, genre-agnostic play/score/game-over state machine. Every
    /// generated game has exactly one of these in its scene; genre-specific
    /// gameplay scripts (e.g. Gameplay/Runner) drive it through this public
    /// API instead of owning score/game-over state themselves.
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        public enum GameState { Ready, Playing, GameOver }

        public static GameManager Instance { get; private set; }

        [SerializeField] private string gameId = "game01";

        public GameState CurrentState { get; private set; } = GameState.Ready;

        /// <summary>
        /// The run's headline metric and the one saved as the best record. For
        /// a Runner that is distance travelled, fed by RunnerDistanceTracker
        /// through SetScore; other genres can drive it with AddScore instead.
        /// </summary>
        public int Score { get; private set; }

        /// <summary>
        /// Coins picked up during this run. Deliberately separate from Score:
        /// coins are the shop currency, so tying them to the record would mean
        /// a long run paid out even with nothing collected. Reset by StartGame,
        /// still readable during the GameOver event.
        /// </summary>
        public int Coins { get; private set; }

        /// <summary>The best score as it stood BEFORE this run ended. Only meaningful once GameOver has fired.</summary>
        public int PreviousBest { get; private set; }

        /// <summary>True when the run that just ended beat PreviousBest. Only meaningful once GameOver has fired.</summary>
        public bool IsNewBest { get; private set; }

        public string GameId => gameId;

        /// <summary>
        /// Survives a scene reload (an instance field would not, since reload
        /// destroys and recreates every GameObject) so RestartGame can skip
        /// the title screen while returning Home does not.
        /// </summary>
        private static bool autoStartOnLoad;

        private static AudioClip gameOverClip;

        /// <summary>Raised whenever Score changes, with the new total.</summary>
        public event Action<int> ScoreChanged;

        /// <summary>Raised whenever Coins changes, with the new run total.</summary>
        public event Action<int> CoinsChanged;

        /// <summary>Raised once when the run ends, with (finalScore, bestScore).</summary>
        public event Action<int, int> GameOver;

        /// <summary>Set by GameFactoryGenerator when wiring a freshly generated scene.</summary>
        public void SetGameId(string id) => gameId = id;

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }

            Instance = this;

            // A HitStop coroutine (RunnerPlayerController) can be cut short by
            // a scene reload before it restores Time.timeScale, so every fresh
            // load unconditionally resets it - not just the StartGame() path below.
            Time.timeScale = 1f;

            // Stays on the title screen (GameState.Ready, its default) unless
            // GameUIController's Play button calls StartGame(), or a restart
            // requested skipping straight back into gameplay.
            if (autoStartOnLoad)
            {
                autoStartOnLoad = false;
                StartGame();
            }
        }

        public void StartGame()
        {
            Score = 0;
            Coins = 0;
            IsNewBest = false;
            CurrentState = GameState.Playing;
            Time.timeScale = 1f;
            ScoreChanged?.Invoke(Score);
            CoinsChanged?.Invoke(Coins);
        }

        public void AddScore(int amount)
        {
            if (CurrentState != GameState.Playing) return;

            Score += amount;
            ScoreChanged?.Invoke(Score);
        }

        /// <summary>
        /// Sets Score to an externally measured value, for metrics that are
        /// sampled rather than accumulated (distance travelled). Ignores a
        /// lower value so the score never counts backwards when the player is
        /// knocked back, and stays silent when nothing changed - this is
        /// called every frame, and firing ScoreChanged on every one of them
        /// would rebuild the score label 60 times a second.
        /// </summary>
        public void SetScore(int value)
        {
            if (CurrentState != GameState.Playing) return;
            if (value <= Score) return;

            Score = value;
            ScoreChanged?.Invoke(Score);
        }

        public void AddCoins(int amount)
        {
            if (CurrentState != GameState.Playing) return;

            Coins += amount;
            CoinsChanged?.Invoke(Coins);
        }

        public void TriggerGameOver()
        {
            if (CurrentState != GameState.Playing) return;

            CurrentState = GameState.GameOver;

            // Read before saving: SaveBestScore returns the NEW best, which is
            // the run's own score on a record run, so the "이전 최고" line and
            // the 신기록 badge would both be wrong if derived from it.
            PreviousBest = SaveSystem.GetBestScore(gameId);
            IsNewBest = Score > PreviousBest;
            int best = SaveSystem.SaveBestScore(gameId, Score);

            // Currency comes from coins, not from the score. Those were the
            // same number while Score WAS the coin count; now that Score is
            // distance, paying out distance would hand out currency for
            // running past coins without collecting any of them.
            SaveSystem.SaveInt(gameId, ShopKeys.Currency, SaveSystem.GetInt(gameId, ShopKeys.Currency) + Coins);

            if (gameOverClip == null) gameOverClip = ProceduralTone.Sine("SFX_GameOver", 220f, 0.35f);
            AudioManager.Instance?.PlaySfx(gameOverClip);

            GameOver?.Invoke(Score, best);
        }

        /// <summary>Reloads the scene and jumps straight back into gameplay, skipping the title screen.</summary>
        public void RestartGame()
        {
            autoStartOnLoad = true;
            SceneController.ReloadCurrent();
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }
    }
}

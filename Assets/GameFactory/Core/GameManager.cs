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
        public int Score { get; private set; }
        public string GameId => gameId;

        /// <summary>Raised whenever Score changes, with the new total.</summary>
        public event Action<int> ScoreChanged;

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
        }

        private void Start()
        {
            StartGame();
        }

        public void StartGame()
        {
            Score = 0;
            CurrentState = GameState.Playing;
            Time.timeScale = 1f;
            ScoreChanged?.Invoke(Score);
        }

        public void AddScore(int amount)
        {
            if (CurrentState != GameState.Playing) return;

            Score += amount;
            ScoreChanged?.Invoke(Score);
        }

        public void TriggerGameOver()
        {
            if (CurrentState != GameState.Playing) return;

            CurrentState = GameState.GameOver;
            int best = SaveSystem.SaveBestScore(gameId, Score);
            GameOver?.Invoke(Score, best);
        }

        public void RestartGame()
        {
            SceneController.ReloadCurrent();
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }
    }
}

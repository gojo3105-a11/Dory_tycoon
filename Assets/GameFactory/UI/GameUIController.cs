using GameFactory.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GameFactory.UI
{
    /// <summary>
    /// Single UI orchestrator for a generated game: live score, and on game
    /// over a panel with the final/best score and a restart button. Reads
    /// only GameManager's public events/API - it holds no gameplay state.
    /// </summary>
    public class GameUIController : MonoBehaviour
    {
        [SerializeField] private Text scoreText;
        [SerializeField] private GameObject gameOverPanel;
        [SerializeField] private Text finalScoreText;
        [SerializeField] private Text bestScoreText;
        [SerializeField] private Button restartButton;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetReferences(Text score, GameObject gameOver, Text finalScore, Text bestScore, Button restart)
        {
            scoreText = score;
            gameOverPanel = gameOver;
            finalScoreText = finalScore;
            bestScoreText = bestScore;
            restartButton = restart;
        }

        private void Start()
        {
            if (gameOverPanel != null) gameOverPanel.SetActive(false);
            if (restartButton != null) restartButton.onClick.AddListener(HandleRestartClicked);

            GameManager manager = GameManager.Instance;
            if (manager == null) return;

            manager.ScoreChanged += HandleScoreChanged;
            manager.GameOver += HandleGameOver;
            HandleScoreChanged(manager.Score);
        }

        private void OnDestroy()
        {
            GameManager manager = GameManager.Instance;
            if (manager == null) return;

            manager.ScoreChanged -= HandleScoreChanged;
            manager.GameOver -= HandleGameOver;
        }

        private void HandleScoreChanged(int score)
        {
            if (scoreText != null) scoreText.text = score.ToString();
        }

        private void HandleGameOver(int finalScore, int bestScore)
        {
            if (gameOverPanel != null) gameOverPanel.SetActive(true);
            if (finalScoreText != null) finalScoreText.text = $"Score: {finalScore}";
            if (bestScoreText != null) bestScoreText.text = $"Best: {bestScore}";
        }

        private void HandleRestartClicked()
        {
            GameManager.Instance?.RestartGame();
        }
    }
}

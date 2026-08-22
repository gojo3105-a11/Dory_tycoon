using UnityEngine.SceneManagement;

namespace GameFactory.Core
{
    /// <summary>Small wrapper so gameplay code never calls SceneManager directly.</summary>
    public static class SceneController
    {
        public static void ReloadCurrent()
        {
            Scene current = SceneManager.GetActiveScene();
            SceneManager.LoadScene(current.buildIndex);
        }

        public static void LoadScene(string sceneName)
        {
            SceneManager.LoadScene(sceneName);
        }
    }
}

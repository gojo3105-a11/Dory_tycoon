using System.Collections;
using UnityEngine;

namespace GameFactory.UI
{
    /// <summary>
    /// Fades a full-screen UI panel in/out instead of an instant SetActive.
    /// Show()/Hide() are meant to replace gameObject.SetActive(true/false) at
    /// the call sites that react to a user action (Play, Home, open/close
    /// Shop) - the very first inactive/active state at scene load is still
    /// set directly by SceneGenerator, since there is nothing to animate
    /// away from at that point.
    /// </summary>
    [RequireComponent(typeof(CanvasGroup))]
    public class PanelTransition : MonoBehaviour
    {
        [SerializeField] private float fadeDuration = 0.15f;

        private CanvasGroup canvasGroup;
        private Coroutine activeRoutine;

        private void Awake()
        {
            canvasGroup = GetComponent<CanvasGroup>();
        }

        public void Show()
        {
            gameObject.SetActive(true);
            canvasGroup.interactable = true;
            canvasGroup.blocksRaycasts = true;
            RestartFade(canvasGroup.alpha, 1f, false);
        }

        public void Hide()
        {
            canvasGroup.interactable = false;
            canvasGroup.blocksRaycasts = false;
            RestartFade(canvasGroup.alpha, 0f, true);
        }

        private void RestartFade(float from, float to, bool deactivateOnFinish)
        {
            if (activeRoutine != null) StopCoroutine(activeRoutine);
            activeRoutine = StartCoroutine(FadeRoutine(from, to, deactivateOnFinish));
        }

        private IEnumerator FadeRoutine(float from, float to, bool deactivateOnFinish)
        {
            float elapsed = 0f;
            canvasGroup.alpha = from;
            while (elapsed < fadeDuration)
            {
                elapsed += Time.unscaledDeltaTime;
                canvasGroup.alpha = Mathf.Lerp(from, to, elapsed / fadeDuration);
                yield return null;
            }

            canvasGroup.alpha = to;
            if (deactivateOnFinish) gameObject.SetActive(false);
            activeRoutine = null;
        }
    }
}

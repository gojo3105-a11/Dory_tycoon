using System.Collections;
using UnityEngine;
using UnityEngine.EventSystems;

namespace GameFactory.UI
{
    /// <summary>Scales a button down on press and eases it back on release - a lightweight touch-feedback beat with no external assets.</summary>
    public class ButtonPunchFeedback : MonoBehaviour, IPointerDownHandler, IPointerUpHandler
    {
        [SerializeField] private float pressedScale = 0.92f;
        [SerializeField] private float returnDuration = 0.1f;

        private Vector3 originalScale;
        private Coroutine activeRoutine;

        private void Awake()
        {
            originalScale = transform.localScale;
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            if (activeRoutine != null) StopCoroutine(activeRoutine);
            transform.localScale = originalScale * pressedScale;
        }

        public void OnPointerUp(PointerEventData eventData)
        {
            if (activeRoutine != null) StopCoroutine(activeRoutine);
            activeRoutine = StartCoroutine(ReturnToOriginalScale());
        }

        private IEnumerator ReturnToOriginalScale()
        {
            Vector3 start = transform.localScale;
            float elapsed = 0f;
            while (elapsed < returnDuration)
            {
                elapsed += Time.unscaledDeltaTime;
                transform.localScale = Vector3.Lerp(start, originalScale, elapsed / returnDuration);
                yield return null;
            }

            transform.localScale = originalScale;
            activeRoutine = null;
        }
    }
}

using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>Generic 2D camera follow usable by any genre (Runner follows X only, Puzzle can lock both axes).</summary>
    public class CameraFollow2D : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Vector3 offset = new Vector3(2f, 0f, -10f);
        [SerializeField] private bool followX = true;
        [SerializeField] private bool followY;
        [SerializeField] private float smoothTime = 0.15f;

        private Vector3 velocity;
        private Vector3 basePosition;
        private float shakeTimeRemaining;
        private float shakeMagnitude;

        public void SetTarget(Transform newTarget) => target = newTarget;

        /// <summary>Briefly offsets the rendered camera position with random jitter, decaying to zero over duration.</summary>
        public void Shake(float duration, float magnitude)
        {
            shakeTimeRemaining = duration;
            shakeMagnitude = magnitude;
        }

        private void Awake()
        {
            basePosition = transform.position;
        }

        private void LateUpdate()
        {
            if (target == null) return;

            Vector3 desired = basePosition;
            if (followX) desired.x = target.position.x + offset.x;
            if (followY) desired.y = target.position.y + offset.y;
            desired.z = offset.z;

            // Shake is applied on top of basePosition, not baked into it, so
            // SmoothDamp keeps chasing the real follow target instead of the
            // jittered render position from the previous frame.
            basePosition = Vector3.SmoothDamp(basePosition, desired, ref velocity, smoothTime);

            Vector3 shakeOffset = Vector3.zero;
            if (shakeTimeRemaining > 0f)
            {
                shakeTimeRemaining -= Time.unscaledDeltaTime;
                shakeOffset = (Vector3)(Random.insideUnitCircle * shakeMagnitude);
            }

            transform.position = basePosition + shakeOffset;
        }
    }
}
